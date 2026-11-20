"""Preço probabilístico: três pontos por item, fator de projeto correlacionado e Monte Carlo.

Um orçamento de número único esconde o risco. Aqui cada item de trabalho do dossiê tem horas em três
pontos (otimista, provável, pessimista), e a simulação devolve faixas: P50 (enxuto), P80 (recomendado) e
P95 (seguro), em horas, custo e prazo.

Modelo, de propósito simples e explícito:
- Cada item segue uma distribuição PERT (beta com lambda 4) entre otimista e pessimista, com moda no provável.
- O risco alarga o pessimista, não o provável: cada risco declarado no item multiplica a distância entre
  provável e pessimista por (1 + peso do risco). Os pesos ficam no arquivo de entrada, nunca escondidos aqui.
- Os itens não são independentes. O mesmo cliente, a mesma ambiguidade e a mesma equipe afetam todos de uma
  vez. Se a simulação tratasse cada item como independente, os erros se cancelariam e a cauda sumiria. Por
  isso um fator de projeto, lognormal com mediana 1, é sorteado uma vez por rodada e multiplica as horas de
  todos os itens.
- Custos fora de hora (tokens, infraestrutura) também têm três pontos. Os que crescem com o trabalho
  (`acompanha_fator = true`) recebem o mesmo fator.

As taxas, os pesos calibrados e o histórico real são ativos comerciais e não moram neste repositório.
O exemplo público é fictício.
"""
from __future__ import annotations

import csv
import math
import random
import statistics
import tomllib
from dataclasses import dataclass
from pathlib import Path

PRIORIDADES = ("essencial", "importante", "desejavel")
PERCENTIS = (50, 80, 95)
LAMBDA_PERT = 4.0
MINIMO_CALIBRACAO = 10


class ErroPreco(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    nome: str
    categoria: str
    prioridade: str
    otimista: float
    provavel: float
    pessimista: float  # já alargado pelos riscos
    riscos: tuple[str, ...]


@dataclass(frozen=True)
class Custo:
    nome: str
    otimista: float
    provavel: float
    pessimista: float
    acompanha_fator: bool


@dataclass(frozen=True)
class Modelo:
    moeda: str
    taxa_hora: float
    horas_por_semana: float
    rodadas: int
    semente: int
    sigma_fator: float
    itens: tuple[Item, ...]
    custos: tuple[Custo, ...]


@dataclass(frozen=True)
class Simulacao:
    modelo: Modelo
    horas_por_item: tuple[tuple[float, ...], ...]  # [item][rodada], já com o fator
    custos_extras: tuple[float, ...]  # [rodada]

    def custo(self, indices: list[int] | range | None = None) -> list[float]:
        indices = range(len(self.modelo.itens)) if indices is None else indices
        taxa = self.modelo.taxa_hora
        return [sum(self.horas_por_item[i][r] for i in indices) * taxa + self.custos_extras[r]
                for r in range(self.modelo.rodadas)]

    def horas(self) -> list[float]:
        return [sum(coluna) for coluna in zip(*self.horas_por_item, strict=True)]


def alargar(provavel: float, pessimista: float, pesos: list[float]) -> float:
    return provavel + (pessimista - provavel) * (1 + sum(pesos))


def _tres_pontos(valor: object, onde: str) -> tuple[float, float, float]:
    if not (isinstance(valor, list) and len(valor) == 3 and all(isinstance(v, int | float) for v in valor)):
        raise ErroPreco(f"{onde}: precisa ser [otimista, provável, pessimista]")
    o, m, p = (float(v) for v in valor)
    if not 0 <= o <= m <= p:
        raise ErroPreco(f"{onde}: precisa de 0 ≤ otimista ≤ provável ≤ pessimista, veio {valor}")
    return o, m, p


def _numero(dados: dict, chave: str, minimo: float, padrao: float | None = None) -> float:
    valor = dados.get(chave, padrao)
    if not isinstance(valor, int | float) or isinstance(valor, bool) or valor < minimo:
        raise ErroPreco(f"'{chave}' precisa ser número ≥ {minimo}")
    return float(valor)


def ler(caminho: Path) -> Modelo:
    try:
        with caminho.open("rb") as f:
            dados = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ErroPreco(f"não consegui ler {caminho}: {e}") from e
    return montar(dados)


def montar(dados: dict) -> Modelo:
    pesos = dados.get("riscos", {})
    if not isinstance(pesos, dict) or not all(isinstance(v, int | float) and v >= 0 for v in pesos.values()):
        raise ErroPreco("[riscos] precisa mapear nome do risco para um peso ≥ 0")
    itens = []
    for n, bruto in enumerate(dados.get("itens", []), start=1):
        onde = f"itens[{n}] ({bruto.get('nome', '?')})"
        prioridade = bruto.get("prioridade")
        if prioridade not in PRIORIDADES:
            raise ErroPreco(f"{onde}: prioridade precisa ser {', '.join(PRIORIDADES)}")
        riscos = tuple(bruto.get("riscos", []))
        desconhecidos = [r for r in riscos if r not in pesos]
        if desconhecidos:
            raise ErroPreco(f"{onde}: risco sem peso em [riscos]: {', '.join(desconhecidos)}")
        o, m, p = _tres_pontos(bruto.get("horas"), f"{onde}.horas")
        itens.append(Item(str(bruto.get("nome", f"item {n}")), str(bruto.get("categoria", "geral")), prioridade,
                          o, m, alargar(m, p, [pesos[r] for r in riscos]), riscos))
    if not itens:
        raise ErroPreco("nenhum item em [[itens]]")
    custos = []
    for n, bruto in enumerate(dados.get("custos", []), start=1):
        o, m, p = _tres_pontos(bruto.get("valor"), f"custos[{n}].valor")
        custos.append(Custo(str(bruto.get("nome", f"custo {n}")), o, m, p, bool(bruto.get("acompanha_fator", False))))
    fator = dados.get("fator_projeto", {})
    rodadas = int(_numero(dados, "rodadas", 1000, 10000))
    return Modelo(
        moeda=str(dados.get("moeda", "BRL")),
        taxa_hora=_numero(dados, "taxa_hora", 0),
        horas_por_semana=_numero(dados, "horas_por_semana", 1),
        rodadas=rodadas,
        semente=int(_numero(dados, "semente", 0, 1)),
        sigma_fator=_numero(fator if isinstance(fator, dict) else {}, "sigma", 0, 0.2),
        itens=tuple(itens),
        custos=tuple(custos),
    )


def sortear_pert(rng: random.Random, o: float, m: float, p: float) -> float:
    if p == o:
        return o
    alfa = 1 + LAMBDA_PERT * (m - o) / (p - o)
    beta = 1 + LAMBDA_PERT * (p - m) / (p - o)
    return o + (p - o) * rng.betavariate(alfa, beta)


def simular(modelo: Modelo) -> Simulacao:
    rng = random.Random(modelo.semente)  # noqa: S311 - simulação reproduzível, não criptografia
    fatores = [math.exp(rng.gauss(0, modelo.sigma_fator)) if modelo.sigma_fator else 1.0
               for _ in range(modelo.rodadas)]
    horas = tuple(tuple(sortear_pert(rng, i.otimista, i.provavel, i.pessimista) * fatores[r]
                        for r in range(modelo.rodadas)) for i in modelo.itens)
    extras = [0.0] * modelo.rodadas
    for c in modelo.custos:
        for r in range(modelo.rodadas):
            valor = sortear_pert(rng, c.otimista, c.provavel, c.pessimista)
            extras[r] += valor * fatores[r] if c.acompanha_fator else valor
    return Simulacao(modelo, horas, tuple(extras))


def percentil(valores: list[float], p: float) -> float:
    """Percentil pelo posto mais próximo: o menor valor que cobre p% das rodadas."""
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(p / 100 * len(ordenados)) - 1)]


def faixas(valores: list[float]) -> dict[int, float]:
    return {p: percentil(valores, p) for p in PERCENTIS}


def contribuicoes(sim: Simulacao) -> list[tuple[str, float]]:
    """Fração da variância das horas totais que cada item explica: cov(item, total) / var(total).

    As frações somam 1. É onde vale gastar mais descoberta: reduzir a incerteza desses itens é o que mais
    estreita o preço.
    """
    total = sim.horas()
    variancia = statistics.pvariance(total)
    if variancia == 0:
        return [(i.nome, 0.0) for i in sim.modelo.itens]
    media_total = statistics.fmean(total)
    saida = []
    for item, amostras in zip(sim.modelo.itens, sim.horas_por_item, strict=True):
        media = statistics.fmean(amostras)
        cov = statistics.fmean((a - media) * (t - media_total) for a, t in zip(amostras, total, strict=True))
        saida.append((item.nome, cov / variancia))
    return sorted(saida, key=lambda x: -x[1])


@dataclass(frozen=True)
class Escopo:
    dentro: tuple[str, ...]
    fora: tuple[str, ...]
    p80: float
    cabe: bool


def escopo_para_orcamento(sim: Simulacao, orcamento: float) -> Escopo:
    """O caminho inverso: o maior conjunto, pela ordem de prioridade, cujo P80 cabe no orçamento.

    O essencial entra inteiro ou o resultado diz que não cabe. Depois, em cada prioridade, os itens entram do
    mais barato ao mais caro enquanto o P80 do conjunto couber. As mesmas rodadas valem para todos os
    conjuntos comparados, então a diferença entre eles é do escopo, não do sorteio.
    """
    itens = sim.modelo.itens
    escolhidos = [n for n, i in enumerate(itens) if i.prioridade == "essencial"]
    p80 = percentil(sim.custo(escolhidos), 80)
    if p80 > orcamento:
        fora = tuple(i.nome for i in itens)
        return Escopo((), fora, p80, cabe=False)
    for prioridade in PRIORIDADES[1:]:
        candidatos = [n for n, i in enumerate(itens) if i.prioridade == prioridade]
        candidatos.sort(key=lambda n: statistics.fmean(sim.horas_por_item[n]))
        for n in candidatos:
            p80_com = percentil(sim.custo([*escolhidos, n]), 80)
            if p80_com <= orcamento:
                escolhidos.append(n)
                p80 = p80_com
    dentro = tuple(itens[n].nome for n in sorted(escolhidos))
    fora = tuple(i.nome for n, i in enumerate(itens) if n not in escolhidos)
    return Escopo(dentro, fora, p80, cabe=True)


@dataclass(frozen=True)
class Calibracao:
    categoria: str
    itens: int
    cobertura_p80: float  # fração dos itens em que o real ficou até o P80 estimado
    razao_mediana: float  # real / provável
    usar_razao: bool  # há itens suficientes para trocar o palpite inicial pela razão medida


def calibrar(caminho: Path, rodadas: int = 10000, semente: int = 1) -> list[Calibracao]:
    """Lê o histórico (item, categoria, otimista, provavel, pessimista, real) e mede o modelo.

    A métrica de qualidade é a cobertura: o P80 cobriu de fato cerca de 80% dos itens? Se cobriu 50%, o
    modelo está otimista, e isso aparece em número. O P80 de cada item vem só dos três pontos dele, sem o
    fator de projeto.
    """
    rng = random.Random(semente)  # noqa: S311 - simulação reproduzível, não criptografia
    por_categoria: dict[str, list[tuple[bool, float]]] = {}
    try:
        with caminho.open(encoding="utf-8", newline="") as f:
            linhas = list(csv.DictReader(f))
    except OSError as e:
        raise ErroPreco(f"não consegui ler {caminho}: {e}") from e
    for n, linha in enumerate(linhas, start=2):
        try:
            o, m, p, real = (float(linha[c]) for c in ("otimista", "provavel", "pessimista", "real"))
        except (KeyError, TypeError, ValueError) as e:
            raise ErroPreco(f"{caminho}:{n}: precisa de otimista, provavel, pessimista e real numéricos") from e
        _tres_pontos([o, m, p], f"{caminho}:{n}")
        p80 = percentil([sortear_pert(rng, o, m, p) for _ in range(rodadas)], 80)
        por_categoria.setdefault(linha.get("categoria") or "geral", []).append((real <= p80, real / m if m else 0))
    saida = []
    for categoria, dados in sorted(por_categoria.items()):
        cobertos = sum(1 for coberto, _ in dados if coberto)
        saida.append(Calibracao(categoria, len(dados), cobertos / len(dados),
                                statistics.median(r for _, r in dados), len(dados) >= MINIMO_CALIBRACAO))
    return saida
