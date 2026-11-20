"""Chamadas ao git usadas pelos checks. Saída sempre em texto, sem cor e sem diff externo."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SHA_NULO = re.compile(r"0{40}|0{64}")


class ErroGit(RuntimeError):
    pass


def rodar(raiz: Path, *args: str) -> str:
    comando = ["git", "-C", str(raiz), "-c", "color.ui=never", "-c", "log.showSignature=false", *args]
    r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
                       check=False)
    if r.returncode != 0:
        raise ErroGit(f"git {args[0]} falhou ({r.returncode}): {r.stderr.strip()}")
    return r.stdout


def revisoes(intervalo: str) -> list[str]:
    """Converte `BASE..HEAD` em argumentos de `git rev-list`/`git log`.

    No push que cria uma branch, o GitHub manda BASE = 000...0; nesse caso vale todo o histórico de HEAD.
    """
    if intervalo.startswith("-"):
        raise ErroGit(f"intervalo inválido: {intervalo!r}")
    base, sep, topo = intervalo.partition("..")
    if not sep or not base or not topo or topo.startswith("."):
        raise ErroGit(f"intervalo precisa ser BASE..HEAD: {intervalo!r}")
    if _SHA_NULO.fullmatch(base):
        return [topo]
    return [f"{base}..{topo}"]
