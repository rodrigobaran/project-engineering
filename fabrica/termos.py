"""Termos proibidos: impede que nome de cliente ou de projeto privado chegue ao repositório público.

A lista não pode morar aqui, porque publicá-la já seria o vazamento. Ela chega pela variável de ambiente
`TERMOS_PROIBIDOS` (um secret do GitHub Actions), um termo por linha; linhas vazias e começadas por `#`
são ignoradas.

O log da CI de um repositório público é público. Por isso a saída mostra onde o termo apareceu e o
número dele na lista, nunca o termo nem o trecho.

A comparação ignora maiúsculas e acentos: `Padaria São João` e `PADARIA SAO JOAO` são o mesmo termo.
"""
from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import git

VARIAVEL = "TERMOS_PROIBIDOS"
MINIMO = 3


class ErroTermos(ValueError):
    pass


@dataclass(frozen=True)
class Achado:
    onde: str
    linha: int  # 0 quando o termo está no nome do arquivo
    termo: int  # posição do termo na lista, a partir de 1


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def carregar(texto: str | None) -> list[str]:
    if texto is None or not texto.strip():
        raise ErroTermos(f"{VARIAVEL} ausente ou vazia: o check falha fechado. Cadastre o secret no repositório.")
    termos = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if len(normalizar(linha)) < MINIMO:
            raise ErroTermos(f"termo {len(termos) + 1} tem menos de {MINIMO} caracteres e casaria em quase tudo")
        termos.append(normalizar(linha))
    if not termos:
        raise ErroTermos(f"{VARIAVEL} não tem nenhum termo")
    return termos


def procurar(onde: str, texto: str, termos: list[str]) -> list[Achado]:
    achados = []
    for n, linha in enumerate(texto.splitlines(), start=1):
        normal = normalizar(linha)
        achados.extend(Achado(onde, n, i) for i, termo in enumerate(termos, start=1) if termo in normal)
    return achados


def _texto_do_arquivo(caminho: Path) -> str | None:
    dados = caminho.read_bytes()
    if b"\0" in dados[:8192]:
        return None  # binário
    return dados.decode("utf-8", errors="replace")


def conferir_arvore(raiz: Path, termos: list[str]) -> list[Achado]:
    achados = []
    for nome in git.rodar(raiz, "ls-files", "-z").split("\0"):
        if not nome:
            continue
        achados.extend(Achado(nome, 0, a.termo) for a in procurar(nome, nome, termos))
        caminho = raiz / nome
        if caminho.is_file() and not caminho.is_symlink():
            texto = _texto_do_arquivo(caminho)
            if texto is not None:
                achados.extend(procurar(nome, texto, termos))
    return achados


def conferir_commits(raiz: Path, intervalo: str, termos: list[str]) -> list[Achado]:
    achados = []
    saida = git.rodar(raiz, "log", "--format=%H%x1f%B%x1e", *git.revisoes(intervalo), "--")
    for bloco in saida.split("\x1e"):
        bloco = bloco.lstrip("\n")
        if not bloco:
            continue
        sha, _, mensagem = bloco.partition("\x1f")
        achados.extend(procurar(f"mensagem do commit {sha[:7]}", mensagem, termos))
    return achados


def conferir_variaveis(nomes: list[str], termos: list[str]) -> list[Achado]:
    achados = []
    for nome in nomes:
        achados.extend(procurar(f"${nome}", os.environ.get(nome, ""), termos))
    return achados
