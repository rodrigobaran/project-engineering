"""Uma chamada de papel, de ponta a ponta: escolha, contagem, teto, nova tentativa, substituto e validação.

O cliente que fala com o fornecedor entra por parâmetro (`Cliente`), e este módulo não abre conexão. Os testes
usam um cliente falso. Regras (ADR 0002):

- Modelo cujo fornecedor não tem cliente é pulado, com o motivo.
- Antes da primeira tentativa em cada modelo, o fornecedor conta a entrada, porque cada um tem o seu
  tokenizador. A contagem decide se a entrada cabe no limite do contexto e entra no custo máximo.
- Antes de cada tentativa, o teto confere o custo máximo da chamada. Teto atingido para a tarefa: não se
  troca para um modelo mais barato em silêncio, porque isso trocaria qualidade por orçamento sem ninguém ver.
- Erro transitório (429, 5xx, sobrecarga, rede) ou recusa: uma nova tentativa, respeitando o retry-after. Na
  segunda falha, ou com retry-after longo demais, o papel passa ao substituto, e a troca vai para o log. O que
  o fornecedor cobrou, mesmo de uma resposta que parou no meio, entra no gasto.
- Saída fora do schema: uma nova tentativa e, depois, o substituto. A saída nunca é consertada aqui.
- Saída truncada no limite de saída para tudo: o `max_saida` do papel está errado, e trocar de modelo
  esconderia isso.
- Qualquer outro erro (chave errada, pedido malformado, limite de gasto do console) para tudo: trocar de
  fornecedor esconderia o defeito.
- Custo real acima do máximo previsto quer dizer que a contagem de entrada estava errada: a chamada para com
  `ErroCusto`, porque o teto deixou de valer.
- Sem candidato que atenda, a tarefa para com `PrecisaHumano`, com o motivo de cada modelo.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from . import esquema
from .custo import (ErroCusto, Livro, Registro, TetoAtingido, Tetos, Uso, autorizar, custo_maximo, custo_real,
                    saida_efetiva)
from .roteamento import ErroRoteamento, Modelo, Roteamento, Tarefa, escolher, excede_contexto

TENTATIVAS_POR_MODELO = 2


@dataclass(frozen=True)
class Prompt:
    """O que vai para o modelo numa chamada de papel: instrução fixa do papel e o material da tarefa."""

    sistema: str
    usuario: str


@dataclass(frozen=True)
class Pedido:
    tarefa: str
    papel: str
    sha: str
    tokens_entrada: int  # estimativa para a escolha; o teto usa a contagem do fornecedor de cada modelo
    max_saida: int
    conteudo: Any  # o que o cliente envia ao fornecedor (um `Prompt`); este módulo não olha
    schema: dict | None = None  # quando há, a saída precisa casar com ele
    fornecedor_autor: str | None = None
    dado_pessoal_cliente: bool = False
    esforco: str | None = None  # low, medium, high...; sem valor, vale o padrão do modelo


@dataclass(frozen=True)
class Resposta:
    saida: Any
    uso: Uso


class ErroTransitorio(Exception):
    """429, 5xx, sobrecarga ou rede. `retry_after` em segundos, quando o fornecedor informa. `uso` vem quando a
    resposta parou no meio e o fornecedor já tinha contado tokens."""

    def __init__(self, motivo: str, retry_after: float | None = None, uso: Uso | None = None):
        super().__init__(motivo)
        self.retry_after = retry_after
        self.uso = uso


class Recusa(Exception):
    """O modelo recusou. A recusa pode ser cobrada, então o uso vem junto quando o fornecedor informa."""

    def __init__(self, motivo: str, uso: Uso | None = None):
        super().__init__(motivo)
        self.uso = uso


class SaidaTruncada(Exception):
    """A saída parou no limite pedido. Foi cobrada, e o uso vem junto."""

    def __init__(self, motivo: str, uso: Uso):
        super().__init__(motivo)
        self.uso = uso


class Cliente(Protocol):
    def atende(self, modelo: Modelo) -> bool: ...

    def contar(self, modelo: Modelo, pedido: Pedido) -> int: ...

    def chamar(self, modelo: Modelo, pedido: Pedido, max_saida: int) -> Resposta: ...


class PrecisaHumano(Exception):
    def __init__(self, papel: str, motivos: list[str]):
        super().__init__(f"{papel}: nenhum modelo atendeu. " + "; ".join(motivos))
        self.motivos = motivos


@dataclass(frozen=True)
class Resultado:
    modelo: Modelo
    saida: Any
    custo_usd: Decimal


def _agora() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Contexto:
    pedido: Pedido
    livro: Livro
    agora: Callable[[], datetime]
    relogio: Callable[[], float]
    motivos: list[str] = field(default_factory=list)

    def registrar(self, modelo: Modelo, tentativa: int, resultado: str, inicio: float | None = None,
                  uso: Uso | None = None, custo: Decimal = Decimal(0), detalhe: str = "") -> None:
        uso = uso or Uso(0, 0)
        duracao = 0.0 if inicio is None else round(self.relogio() - inicio, 3)
        self.livro.registrar(Registro(
            em=self.agora().isoformat(), tarefa=self.pedido.tarefa, papel=self.pedido.papel,
            fornecedor=modelo.fornecedor, modelo=modelo.chave, tentativa=tentativa, resultado=resultado,
            entrada=uso.entrada, saida=uso.saida, cache_leitura=uso.cache_leitura, custo_usd=custo,
            duracao_s=duracao, sha=self.pedido.sha, detalhe=detalhe))

    def cobrado(self, modelo: Modelo, tentativa: int, inicio: float, uso: Uso | None,
                maximo: Decimal | None) -> Decimal:
        """O custo do que o fornecedor cobrou. Acima do máximo previsto, registra e para com `ErroCusto`."""
        custo = custo_real(modelo, uso) if uso is not None else Decimal(0)
        if maximo is not None and custo > maximo:
            self.registrar(modelo, tentativa, "acima_do_maximo", inicio, uso, custo, f"máximo previsto US$ {maximo}")
            raise ErroCusto(f"{modelo.chave}: custo real US$ {custo} acima do máximo previsto US$ {maximo}. "
                            "A contagem de entrada ou o limite de saída estão errados, e o teto deixou de valer")
        return custo


def chamar(pedido: Pedido, roteamento: Roteamento, cliente: Cliente, livro: Livro, tetos: Tetos, *,
           agora: Callable[[], datetime] = _agora, dormir: Callable[[float], None] = time.sleep,
           relogio: Callable[[], float] = time.monotonic) -> Resultado:
    papel = roteamento.papel(pedido.papel)
    if papel.agente:
        raise ErroRoteamento(f"{pedido.papel}: papel de agente roda no executor, não por chamada direta")
    escolha = escolher(roteamento, pedido.papel,
                       Tarefa(pedido.tokens_entrada, pedido.fornecedor_autor, pedido.dado_pessoal_cliente))
    ctx = _Contexto(pedido, livro, agora, relogio)
    ctx.motivos.extend(f"{chave}: {motivo}" for chave, motivo in escolha.pulados)

    for n, modelo in enumerate(escolha.candidatos):
        if not cliente.atende(modelo):
            ctx.motivos.append(f"{modelo.chave}: sem cliente para o fornecedor {modelo.fornecedor}")
            continue
        max_saida = saida_efetiva(modelo, pedido.max_saida)
        maximo: Decimal | None = None
        motivo = ""
        for tentativa in range(1, TENTATIVAS_POR_MODELO + 1):
            inicio = relogio()
            try:
                if maximo is None:
                    tokens = cliente.contar(modelo, pedido)
                    excesso = excede_contexto(roteamento, modelo, tokens)
                    if excesso is not None:
                        motivo = f"{tokens} tokens pela contagem do fornecedor: {excesso}"
                        break
                    maximo = custo_maximo(modelo, tokens, max_saida)
                autorizar(livro, tetos, pedido.tarefa, agora().date(), maximo)
                resposta = cliente.chamar(modelo, pedido, max_saida)
            except TetoAtingido as e:
                ctx.registrar(modelo, tentativa, "bloqueada_teto", detalhe=str(e))
                raise
            except ErroTransitorio as e:
                motivo = f"erro transitório: {e}"
                custo = ctx.cobrado(modelo, tentativa, inicio, e.uso, maximo)
                ctx.registrar(modelo, tentativa, "transitorio", inicio, e.uso, custo, str(e))
                espera = roteamento.espera_padrao_s
                if e.retry_after is not None:
                    espera = max(Decimal(0), Decimal(str(e.retry_after)))
                if tentativa == TENTATIVAS_POR_MODELO or espera > roteamento.espera_maxima_s:
                    break
                dormir(float(espera))
                continue
            except Recusa as e:
                motivo = f"recusa: {e}"
                custo = ctx.cobrado(modelo, tentativa, inicio, e.uso, maximo)
                ctx.registrar(modelo, tentativa, "recusa", inicio, e.uso, custo, str(e))
                continue
            except SaidaTruncada as e:
                custo = ctx.cobrado(modelo, tentativa, inicio, e.uso, maximo)
                ctx.registrar(modelo, tentativa, "truncada", inicio, e.uso, custo, str(e))
                raise
            except Exception as e:
                ctx.registrar(modelo, tentativa, "erro", inicio, detalhe=f"{type(e).__name__}: {e}")
                raise

            custo = ctx.cobrado(modelo, tentativa, inicio, resposta.uso, maximo)
            erros = esquema.validar(resposta.saida, pedido.schema) if pedido.schema is not None else []
            if erros:
                motivo = f"saída fora do schema: {erros[0]}"
                ctx.registrar(modelo, tentativa, "saida_invalida", inicio, resposta.uso, custo, erros[0])
                continue
            ctx.registrar(modelo, tentativa, "ok", inicio, resposta.uso, custo)
            return Resultado(modelo, resposta.saida, custo)

        ctx.motivos.append(f"{modelo.chave}: {motivo}")
        proximo = escolha.candidatos[n + 1].chave if n + 1 < len(escolha.candidatos) else "humano"
        ctx.registrar(modelo, tentativa, "troca", detalhe=f"{modelo.chave} -> {proximo}: {motivo}")

    if escolha.humano_no_fim:
        ctx.motivos.append("a lista do papel termina em humano")
    raise PrecisaHumano(pedido.papel, ctx.motivos)
