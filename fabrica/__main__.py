"""Linha de comando da fábrica.

    python -m fabrica sincronizar <projeto>
    python -m fabrica conferir <projeto>
    python -m fabrica classe <projeto> --base origin/main [--declarada B]
    python -m fabrica classe <projeto> --arquivos src/a.py docs/x.md [--declarada B]

Em `classe`, <projeto> é a raiz do repositório. Com --arquivos, cada arquivo conta como modificado:
remoções e renames só aparecem com --base.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import classe, projeto, sincronizar
from .padroes import normalizar


def _mostravel(caminho: str) -> str:
    """Nome de arquivo que não é UTF-8 vira texto imprimível em vez de derrubar a saída."""
    return caminho.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _classe(a: argparse.Namespace) -> int:
    p = projeto.ler(a.projeto)
    if a.base is not None:
        mudancas = classe.mudancas_do_diff(a.projeto, a.base)
    else:
        mudancas = [classe.Mudanca("M", normalizar(arquivo)) for arquivo in a.arquivos]
    r = classe.classificar(mudancas, p)
    for arquivo, cls, motivo in r.motivos:
        print(f"{cls}  {_mostravel(arquivo)}  ({motivo})")
    efetiva = classe.efetiva(a.declarada, r.classe)
    print(f"classe calculada: {r.classe}; declarada: {a.declarada or '-'}; efetiva: {efetiva}")
    if classe.subiu(a.declarada, r.classe):
        print(f"O diff exige classe {r.classe}, acima da declarada {a.declarada}: o PR volta ao portão.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabrica")
    sub = ap.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("sincronizar", help="copia o conteúdo da fábrica para <projeto>/.fabrica/")
    s.add_argument("projeto", type=Path)

    c = sub.add_parser("conferir", help="falha se <projeto>/.fabrica/ foi editada à mão")
    c.add_argument("projeto", type=Path)

    k = sub.add_parser("classe", help="calcula a classe de risco a partir do diff")
    k.add_argument("projeto", type=Path)
    origem = k.add_mutually_exclusive_group(required=True)
    origem.add_argument("--base", help="ref base do diff, por exemplo origin/main")
    origem.add_argument("--arquivos", nargs="+", help="lista explícita de arquivos alterados")
    k.add_argument("--declarada", choices=sorted(classe.ORDEM), help="classe declarada na triagem ou no plano")

    a = ap.parse_args(argv)
    try:
        if a.comando == "sincronizar":
            escritos = sincronizar.sincronizar(a.projeto)
            print(f"{len(escritos)} arquivos em {a.projeto / sincronizar.PASTA}")
            return 0
        if a.comando == "classe":
            return _classe(a)
        d = sincronizar.conferir(a.projeto)
        for rotulo, itens in (("alterado", d.alterados), ("faltando", d.faltando), ("sobrando", d.sobrando)):
            for item in itens:
                print(f"[{rotulo}] .fabrica/{item}")
        if not d.limpa:
            print("Deriva: .fabrica/ não pode ser editada à mão. Mude na fábrica e sincronize.")
            return 1
        print("OK: .fabrica/ igual à versão registrada")
        return 0
    except (projeto.ErroProjeto, sincronizar.ErroSincronizacao, classe.ErroClasse) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
