"""Casamento de caminhos com padrões estilo gitignore simplificado.

Regras:
- `*` casa qualquer sequência sem `/`.
- `**` casa qualquer sequência, inclusive `/` (zero ou mais diretórios).
- `?` casa um caractere que não seja `/`.
- Padrão terminado em `/` casa o diretório e tudo dentro dele.
- Caminhos são sempre relativos à raiz do repositório, com `/`.
- `ignorar_caixa=True` casa sem diferenciar maiúsculas: no Windows e no macOS, `agents.md` e
  `AGENTS.md` são o mesmo arquivo.
"""
from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _compilar(padrao: str, ignorar_caixa: bool) -> re.Pattern[str]:
    if padrao.endswith("/"):
        padrao += "**"
    partes: list[str] = []
    i = 0
    while i < len(padrao):
        c = padrao[i]
        if padrao.startswith("**/", i):
            partes.append("(?:.*/)?")
            i += 3
        elif padrao.startswith("**", i):
            partes.append(".*")
            i += 2
        elif c == "*":
            partes.append("[^/]*")
            i += 1
        elif c == "?":
            partes.append("[^/]")
            i += 1
        else:
            partes.append(re.escape(c))
            i += 1
    return re.compile("".join(partes) + r"\Z", re.IGNORECASE if ignorar_caixa else 0)


def normalizar(caminho: str) -> str:
    return caminho.replace("\\", "/").removeprefix("./")


def casa(caminho: str, padrao: str, *, ignorar_caixa: bool = False) -> bool:
    return _compilar(padrao, ignorar_caixa).match(normalizar(caminho)) is not None


def casa_algum(caminho: str, padroes: list[str] | tuple[str, ...], *, ignorar_caixa: bool = False) -> bool:
    return any(casa(caminho, p, ignorar_caixa=ignorar_caixa) for p in padroes)
