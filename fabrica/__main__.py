"""Linha de comando da fábrica.

    python -m fabrica sincronizar <projeto>
    python -m fabrica conferir <projeto>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import projeto, sincronizar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabrica")
    sub = ap.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("sincronizar", help="copia o conteúdo da fábrica para <projeto>/.fabrica/")
    s.add_argument("projeto", type=Path)

    c = sub.add_parser("conferir", help="falha se <projeto>/.fabrica/ foi editada à mão")
    c.add_argument("projeto", type=Path)

    a = ap.parse_args(argv)
    try:
        if a.comando == "sincronizar":
            escritos = sincronizar.sincronizar(a.projeto)
            print(f"{len(escritos)} arquivos em {a.projeto / sincronizar.PASTA}")
            return 0
        d = sincronizar.conferir(a.projeto)
        for rotulo, itens in (("alterado", d.alterados), ("faltando", d.faltando), ("sobrando", d.sobrando)):
            for item in itens:
                print(f"[{rotulo}] .fabrica/{item}")
        if not d.limpa:
            print("Deriva: .fabrica/ não pode ser editada à mão. Mude na fábrica e sincronize.")
            return 1
        print("OK: .fabrica/ igual à versão registrada")
        return 0
    except (projeto.ErroProjeto, sincronizar.ErroSincronizacao) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
