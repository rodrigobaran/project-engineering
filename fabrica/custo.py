"""Custo das chamadas: o log JSONL e o teto duro (ADR 0002, decisões 6 e 1).

Cada chamada vira uma linha no log, com o resultado e o custo. Antes de cada chamada, o teto compara o
gasto já feito com o **custo máximo possível** da chamada, e não com o custo esperado: entrada contada
mais a saída máxima pedida, no preço da faixa que vale para essa entrada. Assim o gasto nunca passa do
teto, ao custo de barrar uma chamada que talvez coubesse. A consequência prática é que `max_saida`
vira decisão de custo: 128 mil tokens de saída do Fable 5.2 custam US$ 5,12, mais que o teto de uma tarefa.

O dia do teto diário é o dia em UTC. Linha ilegível no log é erro, nunca é pulada: sem ler o log inteiro,
não há como saber quanto já se gastou.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

from .roteamento import Modelo

MILHAO = Decimal(1_000_000)
SEXTA_CASA = Decimal("0.000001")  # um milionésimo de dólar
VARIAVEL_TAREFA = "ORQ_TETO_TAREFA_USD"
VARIAVEL_DIA = "ORQ_TETO_DIA_USD"


class ErroCusto(ValueError):
    pass


class TetoAtingido(Exception):
    """A chamada não foi feita: o custo máximo dela passaria de um teto."""


@dataclass(frozen=True)
class Uso:
    entrada: int
    saida: int
    cache_leitura: int = 0


def _arredondar(valor: Decimal) -> Decimal:
    """Para cima, na sexta casa: o erro de arredondamento nunca joga a favor do gasto."""
    return valor.quantize(SEXTA_CASA, rounding=ROUND_CEILING)


def _preco(modelo: Modelo):
    if modelo.preco is None:
        raise ErroCusto(f"{modelo.chave}: sem preço declarado")
    return modelo.preco


def saida_efetiva(modelo: Modelo, max_saida: int) -> int:
    if max_saida <= 0:
        raise ErroCusto("max_saida precisa ser positivo")
    return min(max_saida, modelo.saida_max) if modelo.saida_max else max_saida


def custo_maximo(modelo: Modelo, tokens_entrada: int, max_saida: int) -> Decimal:
    """O mais que esta chamada pode custar. `tokens_entrada` é um limite superior, contado antes."""
    entrada, saida, _ = _preco(modelo).vigente(tokens_entrada)
    return _arredondar((tokens_entrada * entrada + saida_efetiva(modelo, max_saida) * saida) / MILHAO)


def custo_real(modelo: Modelo, uso: Uso) -> Decimal:
    entrada, saida, cache = _preco(modelo).vigente(uso.entrada + uso.cache_leitura)
    return _arredondar((uso.entrada * entrada + uso.cache_leitura * cache + uso.saida * saida) / MILHAO)


@dataclass(frozen=True)
class Registro:
    em: str  # ISO 8601 em UTC
    tarefa: str
    papel: str
    fornecedor: str
    modelo: str
    tentativa: int
    resultado: str  # ok, transitorio, recusa, saida_invalida, erro, bloqueada_teto, acima_do_maximo, troca
    entrada: int
    saida: int
    cache_leitura: int
    custo_usd: Decimal
    duracao_s: float
    sha: str
    detalhe: str = ""

    def linha(self) -> str:
        dados = asdict(self)
        dados["custo_usd"] = str(self.custo_usd)
        return json.dumps(dados, ensure_ascii=False, sort_keys=True)

    @property
    def dia(self) -> date:
        return datetime.fromisoformat(self.em).date()


class Livro:
    """O log de custo em JSONL, só de acréscimo."""

    def __init__(self, caminho: Path):
        self.caminho = caminho

    def registrar(self, registro: Registro) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(registro.linha() + "\n")
            f.flush()
            os.fsync(f.fileno())

    def registros(self) -> list[Registro]:
        if not self.caminho.exists():
            return []
        lidos = []
        for n, linha in enumerate(self.caminho.read_text(encoding="utf-8").splitlines(), start=1):
            if not linha.strip():
                continue
            try:
                dados = json.loads(linha)
                dados["custo_usd"] = Decimal(dados["custo_usd"])
                registro = Registro(**dados)
                _ = registro.dia
            except (ValueError, TypeError, KeyError, InvalidOperation) as e:
                raise ErroCusto(f"{self.caminho}:{n}: linha ilegível no log de custo ({e}); "
                                "sem o log inteiro não há como saber o gasto") from e
            lidos.append(registro)
        return lidos

    def gastos(self, tarefa: str, dia: date) -> tuple[Decimal, Decimal]:
        """(gasto da tarefa, gasto do dia em UTC), lendo o log uma vez."""
        da_tarefa = do_dia = Decimal(0)
        for r in self.registros():
            if r.tarefa == tarefa:
                da_tarefa += r.custo_usd
            if r.dia == dia:
                do_dia += r.custo_usd
        return da_tarefa, do_dia


@dataclass(frozen=True)
class Tetos:
    tarefa: Decimal
    dia: Decimal

    @classmethod
    def do_ambiente(cls, ambiente: Mapping[str, str] | None = None) -> Tetos:
        """Lê os tetos das variáveis de ambiente. Faltando um, falha: sem teto, o orquestrador não gasta."""
        ambiente = os.environ if ambiente is None else ambiente
        valores = []
        for nome in (VARIAVEL_TAREFA, VARIAVEL_DIA):
            bruto = ambiente.get(nome, "").strip()
            if not bruto:
                raise ErroCusto(f"{nome} ausente: sem teto, nenhuma chamada é feita")
            try:
                valor = Decimal(bruto)
            except InvalidOperation as e:
                raise ErroCusto(f"{nome}: {bruto!r} não é número") from e
            if not valor.is_finite() or valor <= 0:
                raise ErroCusto(f"{nome}: precisa ser positivo")
            valores.append(valor)
        return cls(*valores)


def autorizar(livro: Livro, tetos: Tetos, tarefa: str, dia: date, maximo: Decimal) -> None:
    """Levanta TetoAtingido quando o gasto já feito mais o máximo da chamada passaria de um teto."""
    da_tarefa, do_dia = livro.gastos(tarefa, dia)
    if da_tarefa + maximo > tetos.tarefa:
        raise TetoAtingido(f"tarefa {tarefa}: gasto US$ {da_tarefa} + máximo da chamada US$ {maximo} "
                           f"passa do teto de US$ {tetos.tarefa}")
    if do_dia + maximo > tetos.dia:
        raise TetoAtingido(f"dia {dia.isoformat()}: gasto US$ {do_dia} + máximo da chamada US$ {maximo} "
                           f"passa do teto de US$ {tetos.dia}")
