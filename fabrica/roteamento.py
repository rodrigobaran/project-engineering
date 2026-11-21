"""Roteamento: qual modelo atende cada papel, em que ordem, e quais regras tiram um candidato da fila.

O arquivo (`orquestrador/roteamento.toml`) diz, por papel, o titular e os substitutos. Este módulo lê o
arquivo com conferência estrita e aplica as regras do ADR 0002 antes de qualquer chamada:

- modelo sem preço ou sem contexto declarado nunca é chamado, porque sem preço o teto não vale;
- o revisor nunca é do fornecedor do autor do PR;
- em projeto de cliente com dado pessoal, sai todo modelo que exige retenção (o Fable 5.2 exige 30 dias);
- acima de 70% do contexto do modelo, a chamada vai para outro com contexto maior.

Um candidato pulado não some: o motivo acompanha a escolha, para que "ninguém pôde atender" venha com a
razão de cada um. O dinheiro é Decimal do começo ao fim: o TOML é lido com `parse_float=Decimal`.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

ARQUIVO = Path(__file__).resolve().parent.parent / "orquestrador" / "roteamento.toml"
HUMANO = "humano"

_CHAVES_RAIZ = {"limite_contexto", "espera_padrao_s", "espera_maxima_s", "executores", "modelos", "papeis"}
_CHAVES_MODELO = {"fornecedor", "id", "contexto", "saida_max", "preco", "sem_retencao_zero"}
_CHAVES_PRECO = {"entrada", "saida", "cache_leitura", "faixa"}
_CHAVES_FAIXA = {"acima_de", "entrada", "saida"}
_CHAVES_PAPEL = {"candidatos", "agente", "revisor"}


class ErroRoteamento(ValueError):
    pass


@dataclass(frozen=True)
class Faixa:
    """Preço que passa a valer quando a entrada da chamada passa de `acima_de` tokens."""

    acima_de: int
    entrada: Decimal
    saida: Decimal


@dataclass(frozen=True)
class Preco:
    entrada: Decimal
    saida: Decimal
    cache_leitura: Decimal | None = None  # sem valor declarado, a leitura de cache custa o preço de entrada
    faixa: Faixa | None = None

    def vigente(self, tokens_entrada: int) -> tuple[Decimal, Decimal, Decimal]:
        """(entrada, saída, leitura de cache) por milhão para uma chamada com essa entrada."""
        if self.faixa is not None and tokens_entrada > self.faixa.acima_de:
            # Acima da faixa, o cache não ganha desconto declarado: cobra-se como entrada, o lado seguro.
            return self.faixa.entrada, self.faixa.saida, self.faixa.entrada
        cache = self.cache_leitura if self.cache_leitura is not None else self.entrada
        return self.entrada, self.saida, cache


@dataclass(frozen=True)
class Modelo:
    chave: str
    fornecedor: str
    id: str
    contexto: int | None
    saida_max: int | None
    preco: Preco | None
    sem_retencao_zero: bool


@dataclass(frozen=True)
class Papel:
    nome: str
    candidatos: tuple[str, ...]
    agente: bool
    revisor: bool


@dataclass(frozen=True)
class Roteamento:
    limite_contexto: Decimal
    espera_padrao_s: Decimal
    espera_maxima_s: Decimal
    executores: dict[str, str]
    modelos: dict[str, Modelo]
    papeis: dict[str, Papel]

    def papel(self, nome: str) -> Papel:
        try:
            return self.papeis[nome]
        except KeyError as e:
            raise ErroRoteamento(f"papel desconhecido: {nome!r}") from e

    def executor(self, modelo: Modelo) -> str:
        return self.executores[modelo.fornecedor]


@dataclass(frozen=True)
class Tarefa:
    """O que a escolha precisa saber sobre a chamada."""

    tokens_entrada: int  # limite superior, contado antes da chamada
    fornecedor_autor: str | None = None  # obrigatório para papel de revisor
    dado_pessoal_cliente: bool = False


@dataclass(frozen=True)
class Escolha:
    candidatos: tuple[Modelo, ...]  # na ordem em que serão tentados
    pulados: tuple[tuple[str, str], ...]  # (modelo, motivo)
    humano_no_fim: bool


def _extra(dados: dict, permitidas: set[str], onde: str) -> None:
    extra = set(dados) - permitidas
    if extra:
        raise ErroRoteamento(f"{onde}: campo não previsto {sorted(extra)}")


def _decimal(valor: Any, onde: str) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, int | Decimal):
        raise ErroRoteamento(f"{onde}: esperava número, veio {valor!r}")
    d = Decimal(valor)
    if not d.is_finite() or d < 0:
        raise ErroRoteamento(f"{onde}: precisa ser número finito e não negativo")
    return d


def _inteiro(valor: Any, onde: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErroRoteamento(f"{onde}: esperava inteiro positivo, veio {valor!r}")
    return valor


def _texto(valor: Any, onde: str) -> str:
    if not isinstance(valor, str) or not valor:
        raise ErroRoteamento(f"{onde}: esperava texto, veio {valor!r}")
    return valor


def _preco(dados: Any, onde: str) -> Preco:
    if not isinstance(dados, dict):
        raise ErroRoteamento(f"{onde}: esperava tabela")
    _extra(dados, _CHAVES_PRECO, onde)
    for chave in ("entrada", "saida"):
        if chave not in dados:
            raise ErroRoteamento(f"{onde}: falta '{chave}'")
    faixa = None
    if "faixa" in dados:
        f = dados["faixa"]
        if not isinstance(f, dict):
            raise ErroRoteamento(f"{onde}.faixa: esperava tabela")
        _extra(f, _CHAVES_FAIXA, f"{onde}.faixa")
        if set(f) != _CHAVES_FAIXA:
            raise ErroRoteamento(f"{onde}.faixa: precisa de {sorted(_CHAVES_FAIXA)}")
        faixa = Faixa(_inteiro(f["acima_de"], f"{onde}.faixa.acima_de"),
                      _decimal(f["entrada"], f"{onde}.faixa.entrada"), _decimal(f["saida"], f"{onde}.faixa.saida"))
    cache = _decimal(dados["cache_leitura"], f"{onde}.cache_leitura") if "cache_leitura" in dados else None
    return Preco(_decimal(dados["entrada"], f"{onde}.entrada"), _decimal(dados["saida"], f"{onde}.saida"), cache, faixa)


def _modelo(chave: str, dados: Any) -> Modelo:
    onde = f"modelos.{chave}"
    if not isinstance(dados, dict):
        raise ErroRoteamento(f"{onde}: esperava tabela")
    _extra(dados, _CHAVES_MODELO, onde)
    for obrigatoria in ("fornecedor", "id"):
        if obrigatoria not in dados:
            raise ErroRoteamento(f"{onde}: falta '{obrigatoria}'")
    retencao = dados.get("sem_retencao_zero", False)
    if not isinstance(retencao, bool):
        raise ErroRoteamento(f"{onde}.sem_retencao_zero: esperava booleano")
    return Modelo(
        chave=chave,
        fornecedor=_texto(dados["fornecedor"], f"{onde}.fornecedor"),
        id=_texto(dados["id"], f"{onde}.id"),
        contexto=_inteiro(dados["contexto"], f"{onde}.contexto") if "contexto" in dados else None,
        saida_max=_inteiro(dados["saida_max"], f"{onde}.saida_max") if "saida_max" in dados else None,
        preco=_preco(dados["preco"], f"{onde}.preco") if "preco" in dados else None,
        sem_retencao_zero=retencao,
    )


def _papel(nome: str, dados: Any, modelos: dict[str, Modelo], executores: dict[str, str]) -> Papel:
    onde = f"papeis.{nome}"
    if not isinstance(dados, dict):
        raise ErroRoteamento(f"{onde}: esperava tabela")
    _extra(dados, _CHAVES_PAPEL, onde)
    candidatos = dados.get("candidatos")
    if not isinstance(candidatos, list) or not candidatos or not all(isinstance(c, str) for c in candidatos):
        raise ErroRoteamento(f"{onde}.candidatos: esperava lista de nomes de modelo")
    if len(set(candidatos)) != len(candidatos):
        raise ErroRoteamento(f"{onde}.candidatos: modelo repetido")
    if HUMANO in candidatos[:-1]:
        raise ErroRoteamento(f"{onde}.candidatos: '{HUMANO}' só vale no fim, porque encerra a lista")
    if candidatos[0] == HUMANO:
        raise ErroRoteamento(f"{onde}.candidatos: o titular precisa ser um modelo")
    agente, revisor = dados.get("agente", False), dados.get("revisor", False)
    if not isinstance(agente, bool) or not isinstance(revisor, bool):
        raise ErroRoteamento(f"{onde}: agente e revisor são booleanos")
    for c in candidatos:
        if c == HUMANO:
            continue
        if c not in modelos:
            raise ErroRoteamento(f"{onde}.candidatos: {c!r} não está em [modelos]")
        if agente and modelos[c].fornecedor not in executores:
            raise ErroRoteamento(f"{onde}: nenhum executor para o fornecedor {modelos[c].fornecedor!r}")
    return Papel(nome, tuple(candidatos), agente, revisor)


def ler(texto: str) -> Roteamento:
    try:
        dados = tomllib.loads(texto, parse_float=Decimal)
    except tomllib.TOMLDecodeError as e:
        raise ErroRoteamento(f"TOML inválido: {e}") from e
    _extra(dados, _CHAVES_RAIZ, "raiz")
    for obrigatoria in ("limite_contexto", "espera_padrao_s", "espera_maxima_s", "modelos", "papeis"):
        if obrigatoria not in dados:
            raise ErroRoteamento(f"raiz: falta '{obrigatoria}'")
    limite = _decimal(dados["limite_contexto"], "limite_contexto")
    if not 0 < limite <= 1:
        raise ErroRoteamento("limite_contexto: precisa estar entre 0 e 1")
    executores = dados.get("executores", {})
    if not isinstance(executores, dict) or not all(isinstance(v, str) for v in executores.values()):
        raise ErroRoteamento("executores: esperava tabela de fornecedor para ferramenta")
    if not isinstance(dados["modelos"], dict) or not isinstance(dados["papeis"], dict):
        raise ErroRoteamento("modelos e papeis precisam ser tabelas")
    modelos = {chave: _modelo(chave, m) for chave, m in dados["modelos"].items()}
    if HUMANO in modelos:
        raise ErroRoteamento(f"modelos: '{HUMANO}' é reservado")
    papeis = {nome: _papel(nome, p, modelos, executores) for nome, p in dados["papeis"].items()}
    return Roteamento(limite, _decimal(dados["espera_padrao_s"], "espera_padrao_s"),
                      _decimal(dados["espera_maxima_s"], "espera_maxima_s"), dict(executores), modelos, papeis)


def carregar(caminho: Path = ARQUIVO) -> Roteamento:
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as e:
        raise ErroRoteamento(f"não consegui ler {caminho}: {e}") from e
    return ler(texto)


def _motivo(r: Roteamento, papel: Papel, modelo: Modelo, tarefa: Tarefa) -> str | None:
    """Por que este modelo não pode atender esta chamada; None quando pode."""
    if modelo.preco is None:
        return "sem preço declarado: o teto de custo não teria como valer"
    if modelo.contexto is None:
        return "sem contexto declarado"
    if papel.revisor and modelo.fornecedor == tarefa.fornecedor_autor:
        return f"mesmo fornecedor do autor ({modelo.fornecedor})"
    if tarefa.dado_pessoal_cliente and modelo.sem_retencao_zero:
        return "exige retenção de dados, e o projeto tem dado pessoal de cliente"
    return excede_contexto(r, modelo, tarefa.tokens_entrada)


def excede_contexto(r: Roteamento, modelo: Modelo, tokens_entrada: int) -> str | None:
    """O motivo quando a entrada passa do limite do contexto do modelo; None quando cabe."""
    if modelo.contexto is None:
        return "sem contexto declarado"
    if tokens_entrada > r.limite_contexto * modelo.contexto:
        return f"a entrada passa de {r.limite_contexto:%} do contexto ({modelo.contexto} tokens)"
    return None


def escolher(r: Roteamento, nome_papel: str, tarefa: Tarefa) -> Escolha:
    papel = r.papel(nome_papel)
    if papel.revisor and not tarefa.fornecedor_autor:
        raise ErroRoteamento(f"{nome_papel}: revisor sem o fornecedor do autor não tem como aplicar a regra")
    if tarefa.tokens_entrada < 0:
        raise ErroRoteamento("tokens_entrada não pode ser negativo")
    candidatos: list[Modelo] = []
    pulados: list[tuple[str, str]] = []
    humano = False
    for chave in papel.candidatos:
        if chave == HUMANO:
            humano = True
            break
        modelo = r.modelos[chave]
        motivo = _motivo(r, papel, modelo, tarefa)
        if motivo is None:
            candidatos.append(modelo)
        else:
            pulados.append((chave, motivo))
    return Escolha(tuple(candidatos), tuple(pulados), humano)
