"""Espelho em inglês: `en/<caminho>` traduz cada `.md` em português, e a CI aponta quando ficou para trás.

O português é a fonte. A primeira linha de cada arquivo em `en/` registra de qual arquivo ele é tradução e
o sha256 do português naquele momento:

    <!-- mirror of padrao/NUCLEO.md sha256:<64 hex>; edit the Portuguese source first -->

Mudou o português e o hash não bate: a tradução está desatualizada e a conferência falha. Depois de
atualizar a tradução, `fabrica espelho carimbar <arquivo>` grava o hash novo. O carimbo não prova que a
tradução está certa; prova que alguém a tocou no mesmo PR, e é isso que o revisor confere.

O hash normaliza fim de linha (CRLF vira LF), para o mesmo texto ter o mesmo hash no Windows.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import git

PASTA = "en"
_CABECALHO = re.compile(r"<!-- mirror of (\S+) sha256:([0-9a-f]{64}); edit the Portuguese source first -->")


class ErroEspelho(ValueError):
    pass


@dataclass
class Relatorio:
    faltando: list[str] = field(default_factory=list)  # fonte sem tradução
    desatualizados: list[str] = field(default_factory=list)  # hash não bate
    sem_cabecalho: list[str] = field(default_factory=list)  # en/ sem a linha de origem, ou apontando outro arquivo
    orfaos: list[str] = field(default_factory=list)  # en/ cuja fonte não existe mais

    @property
    def limpo(self) -> bool:
        return not (self.faltando or self.desatualizados or self.sem_cabecalho or self.orfaos)


def hash_fonte(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def cabecalho(fonte: str, sha: str) -> str:
    return f"<!-- mirror of {fonte} sha256:{sha}; edit the Portuguese source first -->"


def _markdown_do_repositorio(raiz: Path) -> list[str]:
    saida = git.rodar(raiz, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md")
    return sorted({n for n in saida.split("\0") if n and (raiz / n).is_file()})


def conferir(raiz: Path) -> Relatorio:
    todos = _markdown_do_repositorio(raiz)
    fontes = [n for n in todos if not n.startswith(f"{PASTA}/")]
    traducoes = {n.removeprefix(f"{PASTA}/") for n in todos if n.startswith(f"{PASTA}/")}
    r = Relatorio()
    for fonte in fontes:
        if fonte not in traducoes:
            r.faltando.append(fonte)
            continue
        primeira = (raiz / PASTA / fonte).read_text(encoding="utf-8").split("\n", 1)[0].strip()
        m = _CABECALHO.fullmatch(primeira)
        if m is None or m.group(1) != fonte:
            r.sem_cabecalho.append(f"{PASTA}/{fonte}")
        elif m.group(2) != hash_fonte(raiz / fonte):
            r.desatualizados.append(f"{PASTA}/{fonte}")
    r.orfaos = sorted(f"{PASTA}/{t}" for t in traducoes - set(fontes))
    return r


def carimbar(raiz: Path, fonte: str) -> str:
    """Grava na tradução o hash atual da fonte. Devolve o caminho da tradução."""
    fonte = fonte.replace("\\", "/").removeprefix("./").removeprefix(f"{PASTA}/")
    origem = raiz / fonte
    traducao = raiz / PASTA / fonte
    if not origem.is_file():
        raise ErroEspelho(f"fonte não existe: {fonte}")
    if not traducao.is_file():
        raise ErroEspelho(f"tradução não existe: {PASTA}/{fonte}. Escreva a tradução antes de carimbar.")
    texto = traducao.read_text(encoding="utf-8")
    primeira, _, resto = texto.partition("\n")
    if _CABECALHO.fullmatch(primeira.strip()) is None:
        resto = texto
    traducao.write_text(cabecalho(fonte, hash_fonte(origem)) + "\n" + resto, encoding="utf-8", newline="")
    return f"{PASTA}/{fonte}"
