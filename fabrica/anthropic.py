"""Cliente da API da Anthropic (Messages), só com a biblioteca padrão.

Fala HTTP direto, sem o SDK oficial: o SDK seria dependência nova (exige ADR) e faz nova tentativa sozinho,
o que duplicaria a regra de `chamada.py`. Referências: https://platform.claude.com/docs/en/api/messages/create,
https://platform.claude.com/docs/en/api/errors e https://platform.claude.com/docs/en/build-with-claude/token-counting

- A chamada usa streaming (SSE). Um pedido longo pode gerar por muitos minutos, e sem streaming a conexão
  fica muda até o fim. O tempo limite do transporte vale entre um pedaço e outro, e a API manda `ping`.
- O pensamento fica no padrão do modelo (adaptativo nos modelos atuais). O esforço vai quando o pedido traz.
- Com schema, a saída é restrita pela API (`output_config.format`) e validada de novo em `chamada.py`. As
  palavras que a API não aceita saem do schema enviado, e o validador local continua conferindo todas.
- O `fallbacks` do servidor fica desligado: ele trocaria de modelo dentro da chamada, com outro preço, fora
  da tabela de roteamento e do log.
- Erros: 408, 429 e 5xx são transitórios (salvo `x-should-retry: false`). O 429 do limite de gasto do console
  é definitivo, porque é um teto. Os outros 4xx são definitivos.
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Iterator, Mapping
from typing import Any

from .chamada import ErroTransitorio, Pedido, Prompt, Recusa, Resposta, SaidaTruncada
from .custo import Uso
from .roteamento import Modelo
from .transporte import ErroRede, Requisicao, RespostaHttp, Transporte, TransporteUrllib

FORNECEDOR = "anthropic"
URL = "https://api.anthropic.com/v1"
VERSAO = "2026-10-21"
VARIAVEL_CHAVE = "ANTHROPIC_API_KEY"
MARGEM_CONTAGEM = 1.02  # a contagem é estimativa do fornecedor; o teto pede um limite superior
LIMITE_DE_GASTO = "enforced_spend_limit_reached"
# Palavras do nosso subconjunto de JSON Schema que a saída estruturada da API não aceita. Elas saem do schema
# enviado, e a validação local em `chamada.py` continua conferindo.
_FORA_DA_API = {"minLength", "minItems", "pattern"}


class ErroFornecedor(Exception):
    """Erro definitivo do fornecedor: chave, permissão, pedido malformado, modelo inexistente, limite de gasto."""

    def __init__(self, motivo: str, status: int | None = None, tipo: str | None = None):
        super().__init__(motivo)
        self.status = status
        self.tipo = tipo


def schema_para_api(schema: Any) -> Any:
    """Cópia do schema no formato que a API aceita: sem as palavras de fora e com objetos fechados."""
    if isinstance(schema, list):
        return [schema_para_api(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    copia = {}
    for chave, valor in schema.items():
        if chave in _FORA_DA_API:
            continue
        if chave in ("properties", "$defs"):
            copia[chave] = {nome: schema_para_api(sub) for nome, sub in valor.items()}
        else:
            copia[chave] = schema_para_api(valor)
    if copia.get("type") == "object":
        copia["additionalProperties"] = False
    return copia


def _uso(bruto: Mapping[str, Any]) -> Uso:
    # A escrita de cache custa até 2 vezes a entrada (TTL de 1 h). Este cliente não pede cache; se a API
    # registrar escrita mesmo assim, ela conta como entrada dobrada, o lado seguro.
    escrita = int(bruto.get("cache_creation_input_tokens") or 0)
    return Uso(entrada=int(bruto.get("input_tokens") or 0) + 2 * escrita,
               saida=int(bruto.get("output_tokens") or 0),
               cache_leitura=int(bruto.get("cache_read_input_tokens") or 0))


def _eventos(linhas: Iterator[str]) -> Iterator[tuple[str, dict]]:
    """Eventos SSE como (nome, dados). Linha `data:` que não é JSON é erro do fornecedor. Um evento sem a linha
    em branco final é descartado, como manda o SSE; quem chama percebe pela falta do `message_stop`."""
    nome, dados = "", []
    for linha in linhas:
        if linha == "":
            if dados:
                bruto = "\n".join(dados)
                try:
                    yield nome or "message", json.loads(bruto)
                except json.JSONDecodeError as e:
                    raise ErroFornecedor(f"evento SSE ilegível ({nome}): {bruto[:200]!r}") from e
            nome, dados = "", []
        elif linha.startswith(":"):
            continue
        elif linha.startswith("event:"):
            nome = linha[6:].strip()
        elif linha.startswith("data:"):
            dados.append(linha[5:].lstrip())


class ClienteAnthropic:
    def __init__(self, chave: str, transporte: Transporte | None = None, *, url: str = URL,
                 tempo_limite_s: float = 300.0):
        if not chave.strip():
            raise ErroFornecedor(f"{VARIAVEL_CHAVE} ausente: sem chave, nenhuma chamada é feita")
        self._chave = chave.strip()
        self.transporte = transporte or TransporteUrllib()
        self.url = url.rstrip("/")
        self.tempo_limite_s = tempo_limite_s

    def __repr__(self) -> str:  # nunca mostra a chave
        return f"ClienteAnthropic({self.url!r})"

    @classmethod
    def do_ambiente(cls, ambiente: Mapping[str, str] | None = None,
                    transporte: Transporte | None = None) -> ClienteAnthropic:
        ambiente = os.environ if ambiente is None else ambiente
        return cls(ambiente.get(VARIAVEL_CHAVE, ""), transporte)

    def atende(self, modelo: Modelo) -> bool:
        return modelo.fornecedor == FORNECEDOR

    # --- pedido ----------------------------------------------------------------------------------------

    def _corpo(self, modelo: Modelo, pedido: Pedido) -> dict[str, Any]:
        prompt = pedido.conteudo
        if not isinstance(prompt, Prompt):
            raise TypeError(f"o conteúdo do pedido precisa ser um Prompt, veio {type(prompt).__name__}")
        corpo: dict[str, Any] = {"model": modelo.id, "messages": [{"role": "user", "content": prompt.usuario}]}
        if prompt.sistema:
            corpo["system"] = prompt.sistema
        if pedido.schema is not None:
            corpo["output_config"] = {"format": {"type": "json_schema", "schema": schema_para_api(pedido.schema)}}
        return corpo

    def _enviar(self, caminho: str, corpo: dict[str, Any]) -> RespostaHttp:
        cabecalhos = {"x-api-key": self._chave, "anthropic-version": VERSAO, "content-type": "application/json"}
        requisicao = Requisicao(f"{self.url}/{caminho}", cabecalhos,
                                json.dumps(corpo, ensure_ascii=False).encode("utf-8"), self.tempo_limite_s)
        try:
            resposta = self.transporte.enviar(requisicao)
        except ErroRede as e:
            raise ErroTransitorio(f"rede: {e}") from e
        if resposta.status != 200:
            self._erro(resposta)
        return resposta

    def _erro(self, resposta: RespostaHttp) -> None:
        try:
            corpo = resposta.corpo()
        except ErroRede:
            corpo = ""
        try:
            erro = json.loads(corpo).get("error") or {}
        except (json.JSONDecodeError, AttributeError):
            erro = {}
        tipo = erro.get("type") or "?"
        detalhes = erro.get("details") or {}
        motivo = f"HTTP {resposta.status} {tipo}: {erro.get('message') or corpo[:200]}"
        retry = resposta.cabecalhos.get("retry-after")
        try:
            retry_after = float(retry) if retry is not None else None
        except ValueError:
            retry_after = None
        if resposta.status == 429 and detalhes.get("error_code") == LIMITE_DE_GASTO:
            raise ErroFornecedor(f"limite de gasto do console atingido. {motivo}", resposta.status, tipo)
        if resposta.cabecalhos.get("x-should-retry", "").lower() == "false":
            raise ErroFornecedor(motivo, resposta.status, tipo)
        if resposta.status in (408, 429) or resposta.status >= 500:
            raise ErroTransitorio(motivo, retry_after)
        raise ErroFornecedor(motivo, resposta.status, tipo)

    # --- contagem --------------------------------------------------------------------------------------

    def contar(self, modelo: Modelo, pedido: Pedido) -> int:
        resposta = self._enviar("messages/count_tokens", self._corpo(modelo, pedido))
        try:
            tokens = int(json.loads(resposta.corpo())["input_tokens"])
        except ErroRede as e:
            raise ErroTransitorio(f"rede: {e}") from e
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise ErroFornecedor(f"contagem ilegível: {e}") from e
        return math.ceil(tokens * MARGEM_CONTAGEM)

    # --- chamada ---------------------------------------------------------------------------------------

    def chamar(self, modelo: Modelo, pedido: Pedido, max_saida: int) -> Resposta:
        corpo = self._corpo(modelo, pedido)
        corpo["max_tokens"] = max_saida
        corpo["stream"] = True
        if pedido.esforco is not None:
            corpo.setdefault("output_config", {})["effort"] = pedido.esforco
        resposta = self._enviar("messages", corpo)

        uso: dict[str, int] = {}
        blocos: dict[int, list[str]] = {}
        parada: str | None = None
        detalhes_parada: dict = {}
        terminou = False

        def somar(bruto: Mapping[str, Any] | None) -> None:
            for chave, valor in (bruto or {}).items():  # contagens acumuladas: vale a maior vista
                if isinstance(valor, int) and not isinstance(valor, bool):
                    uso[chave] = max(uso.get(chave, 0), valor)

        try:
            for nome, dados in _eventos(resposta.linhas):
                tipo = dados.get("type", nome)
                if tipo == "message_start":
                    somar(dados.get("message", {}).get("usage"))
                elif tipo == "content_block_start":
                    bloco = dados.get("content_block") or {}
                    if bloco.get("type") == "text":  # pensamento e outros blocos ficam de fora
                        blocos[dados.get("index", 0)] = [bloco.get("text", "")]
                elif tipo == "content_block_delta":
                    delta = dados.get("delta") or {}
                    if delta.get("type") == "text_delta" and dados.get("index", 0) in blocos:
                        blocos[dados.get("index", 0)].append(delta.get("text", ""))
                elif tipo == "message_delta":
                    delta = dados.get("delta") or {}
                    parada = delta.get("stop_reason") or parada
                    detalhes_parada = delta.get("stop_details") or detalhes_parada
                    somar(dados.get("usage"))
                elif tipo == "message_stop":
                    terminou = True
                elif tipo == "error":
                    erro = dados.get("error") or {}
                    motivo = f"erro no meio da resposta: {erro.get('type')}: {erro.get('message')}"
                    if erro.get("type") in ("overloaded_error", "api_error", "rate_limit_error"):
                        raise ErroTransitorio(motivo, uso=_uso(uso))
                    raise ErroFornecedor(motivo, tipo=erro.get("type"))
                # ping e eventos novos: ignorados
        except ErroRede as e:
            raise ErroTransitorio(f"rede: {e}", uso=_uso(uso)) from e
        except ErroTransitorio as e:
            if e.uso is None:
                raise ErroTransitorio(str(e), e.retry_after, _uso(uso)) from e
            raise

        consumo = _uso(uso)
        if not terminou:
            raise ErroTransitorio("o stream acabou sem message_stop", uso=consumo)
        if parada == "refusal":
            categoria = detalhes_parada.get("category") if isinstance(detalhes_parada, dict) else None
            raise Recusa(f"stop_reason refusal (categoria: {categoria or '-'})", consumo)
        if parada in ("max_tokens", "model_context_window_exceeded"):
            raise SaidaTruncada(f"stop_reason {parada} com max_tokens {max_saida}", consumo)
        if parada not in ("end_turn", "stop_sequence"):
            raise ErroFornecedor(f"stop_reason inesperado: {parada!r}")

        texto = "".join("".join(partes) for _, partes in sorted(blocos.items()))
        if pedido.schema is None:
            return Resposta(texto, consumo)
        try:
            return Resposta(json.loads(texto), consumo)
        except json.JSONDecodeError:
            return Resposta(texto, consumo)  # a validação em chamada.py marca como saída inválida
