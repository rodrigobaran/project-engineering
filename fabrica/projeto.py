"""Leitura do `.fabrica/projeto.toml`, o único arquivo de `.fabrica/` que o projeto edita."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MODOS = ("desenvolvimento", "manutencao")
ARQUIVO = Path(".fabrica") / "projeto.toml"


class ErroProjeto(ValueError):
    pass


@dataclass(frozen=True)
class Projeto:
    nome: str
    modo: str
    camada: str
    classe_a: tuple[str, ...] = field(default_factory=tuple)
    classe_c: tuple[str, ...] = field(default_factory=tuple)


def ler(raiz: Path) -> Projeto:
    caminho = raiz / ARQUIVO
    if not caminho.is_file():
        raise ErroProjeto(f"{ARQUIVO} não existe em {raiz}")
    with caminho.open("rb") as f:
        dados = tomllib.load(f)

    def texto(chave: str) -> str:
        valor = dados.get(chave)
        if not isinstance(valor, str) or not valor.strip():
            raise ErroProjeto(f"{ARQUIVO}: '{chave}' é obrigatório e precisa ser texto")
        return valor.strip()

    def lista(secao: dict, chave: str) -> tuple[str, ...]:
        valor = secao.get(chave, [])
        if not isinstance(valor, list) or not all(isinstance(v, str) and v for v in valor):
            raise ErroProjeto(f"{ARQUIVO}: 'classes.{chave}' precisa ser lista de padrões")
        return tuple(valor)

    modo = texto("modo")
    if modo not in MODOS:
        raise ErroProjeto(f"{ARQUIVO}: modo '{modo}' inválido; use {' ou '.join(MODOS)}")
    classes = dados.get("classes", {})
    if not isinstance(classes, dict):
        raise ErroProjeto(f"{ARQUIVO}: [classes] precisa ser uma tabela")
    return Projeto(
        nome=texto("nome"),
        modo=modo,
        camada=texto("camada"),
        classe_a=lista(classes, "a"),
        classe_c=lista(classes, "c"),
    )
