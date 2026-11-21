"""Uma chamada de papel, de ponta a ponta, sem rede: escolha, teto, nova tentativa, substituto e validação.

O cliente que fala com o fornecedor entra por parâmetro (`Cliente`). Este módulo não abre conexão: os
testes usam um cliente falso, e o cliente HTTP de cada fornecedor vem num PR próprio. Regras (ADR 0002):

- Antes de cada tentativa, o teto confere o custo máximo da chamada. Teto atingido para a tarefa: não se
  troca para um modelo mais barato em silêncio, porque isso trocaria qualidade por orçamento sem ninguém ver.
- Erro transitório (429, 5xx, sobrecarga) ou recusa: uma nova tentativa, respeitando o retry-after. Na
  segunda falha, ou com retry-after longo demais, o papel passa ao substituto, e a troca vai para o log.
- Saída fora do schema: uma nova tentativa e, depois, o substituto. A saída nunca é consertada aqui.
- Qualquer outro erro (chave errada, pedido malformado) para tudo: trocar de fornecedor esconderia o defeito.
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
from .roteamento import ErroRoteamento, Modelo, Roteamento, Tarefa, escolher

TENTATIVAS_POR_MODELO = 2


@dataclass(frozen=True)
class Pedido:
    tarefa: str
    papel: str
    sha: str
    tokens_entrada: int  # limite superior, contado antes da chamada
    max_saida: int
    conteudo: Any  # o que o cliente envia ao fornecedor; este módulo não olha
    schema: dict | None = None  # quando há, a saída precisa casar com ele
    fornecedor_autor: str | None = None
    dado_pessoal_cliente: bool = False


@dataclass(frozen=True)
class Resposta:
    saida: Any
    uso: Uso


class ErroTransitorio(Exception):
    """429, 5xx ou sobrecarga. `retry_after` em segundos, quando o fornecedor informa."""

    def __init__(self, motivo: str, retry_after: float | None = None):
        super().__init__(motivo)
        self.retry_after = retry_after


class Recusa(Exception):
    """O modelo recusou. A recusa pode ser cobrada, então o uso vem junto quando o fornecedor informa."""

    def __init__(self, motivo: str, uso: Uso | None = None):
        super().__init__(motivo)
        self.uso = uso


class Cliente(Protocol):
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
        max_saida = saida_efetiva(modelo, pedido.max_saida)
        maximo = custo_maximo(modelo, pedido.tokens_entrada, max_saida)
        motivo = ""
        for tentativa in range(1, TENTATIVAS_POR_MODELO + 1):
            try:
                autorizar(livro, tetos, pedido.tarefa, agora().date(), maximo)
            except TetoAtingido as e:
                ctx.registrar(modelo, tentativa, "bloqueada_teto", detalhe=str(e))
                raise
            inicio = relogio()
            try:
                resposta = cliente.chamar(modelo, pedido, max_saida)
            except ErroTransitorio as e:
                motivo = f"erro transitório: {e}"
                ctx.registrar(modelo, tentativa, "transitorio", inicio, detalhe=str(e))
                espera = roteamento.espera_padrao_s
                if e.retry_after is not None:
                    espera = max(Decimal(0), Decimal(str(e.retry_after)))
                if tentativa == TENTATIVAS_POR_MODELO or espera > roteamento.espera_maxima_s:
                    break
                dormir(float(espera))
                continue
            except Recusa as e:
                motivo = f"recusa: {e}"
                custo = custo_real(modelo, e.uso) if e.uso is not None else Decimal(0)
                if custo > maximo:
                    ctx.registrar(modelo, tentativa, "acima_do_maximo", inicio, e.uso, custo, str(e))
                    raise ErroCusto(f"{modelo.chave}: recusa custou US$ {custo}, acima do máximo previsto") from e
                ctx.registrar(modelo, tentativa, "recusa", inicio, e.uso, custo, str(e))
                continue
            except Exception as e:
                ctx.registrar(modelo, tentativa, "erro", inicio, detalhe=f"{type(e).__name__}: {e}")
                raise

            custo = custo_real(modelo, resposta.uso)
            if custo > maximo:
                ctx.registrar(modelo, tentativa, "acima_do_maximo", inicio, resposta.uso, custo,
                              f"máximo previsto US$ {maximo}")
                raise ErroCusto(f"{modelo.chave}: custo real US$ {custo} acima do máximo previsto US$ {maximo}. "
                                "A contagem de entrada ou o limite de saída estão errados, e o teto deixou de valer")
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
