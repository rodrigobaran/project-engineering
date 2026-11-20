"""Classe de risco de um PR, calculada a partir do diff e não do texto da issue.

A classe decide se o Rodrigo é chamado, então não pode depender da opinião de um LLM. A triagem pode
declarar uma classe antes do código existir; vale a mais severa entre a declarada e a calculada.

- A: toca caminho de portão (fixo para todo projeto), gatilho de ADR (N6), caminho A do projeto, ou
  remove ou move um arquivo de teste.
- C: todos os arquivos casam os padrões C (documentação, por padrão).
- B: o resto.

Na dúvida, o cálculo erra para cima: padrões de A casam sem diferenciar maiúsculas, padrões de C
diferenciam, um rename conta a origem e o destino, e status desconhecido do git é erro, não B.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .padroes import casa_algum, normalizar
from .projeto import Projeto

ORDEM = {"C": 0, "B": 1, "A": 2}

# Caminhos dos próprios portões e das instruções que os agentes leem. Valem em todo projeto, e o
# projeto não consegue removê-los: o `projeto.toml` mora em `.fabrica/`, que também é portão.
PORTOES = (
    ".github/",
    ".fabrica/",
    "**/AGENTS.md",
    "**/CLAUDE.md",
    "**/GEMINI.md",
    ".claude/",
    ".codex/",
    ".gemini/",
    ".cursor/",
    "CODEOWNERS",
    "docs/CODEOWNERS",
    "scripts/verificar",
    "scripts/testar",
)

# Gatilho de ADR (N6): dependência, versão de runtime, registro de pacotes e deploy. Conservador:
# qualquer mudança nesses arquivos é A, inclusive um bump de patch no lockfile.
GATILHOS_ADR = (
    "**/package.json",
    "**/package-lock.json",
    "**/npm-shrinkwrap.json",
    "**/pnpm-lock.yaml",
    "**/yarn.lock",
    "**/bun.lock",
    "**/bun.lockb",
    "**/.npmrc",
    "**/.nvmrc",
    "**/.node-version",
    "**/pyproject.toml",
    "**/requirements*.txt",
    "**/poetry.lock",
    "**/uv.lock",
    "**/Pipfile",
    "**/Pipfile.lock",
    "**/.python-version",
    "**/.tool-versions",
    "**/cpanfile",
    "**/cpanfile.snapshot",
    "**/Dockerfile",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/compose.yml",
    "**/compose.yaml",
    "**/wrangler.toml",
)

# Arquivos de teste. Editar teste é B e o revisor procura enfraquecimento; remover ou mover é A.
TESTES = (
    "**/tests/",
    "**/test/",
    "**/__tests__/",
    "**/e2e/",
    "**/test_*.py",
    "**/*_test.py",
    "**/conftest.py",
    "**/*_test.go",
    "**/*.test.*",
    "**/*.spec.*",
    "**/*.t",
)

C_PADRAO = ("docs/**", "**/*.md")

# Status do `git diff --name-status`: A, C, D, M, R, T. U (conflito) e X (desconhecido) são erro.
_STATUS_UM_CAMINHO = {"A", "D", "M", "T"}
_STATUS_DOIS_CAMINHOS = {"R", "C"}


class ErroClasse(ValueError):
    pass


@dataclass(frozen=True)
class Mudanca:
    status: str  # A, C, D, M, R ou T
    caminho: str
    origem: str | None = None  # só em rename (R) e cópia (C)


@dataclass(frozen=True)
class Resultado:
    classe: str
    motivos: tuple[tuple[str, str, str], ...]  # (arquivo, classe, motivo)


def _classe_do_caminho(caminho: str, projeto: Projeto) -> tuple[str, str]:
    if casa_algum(caminho, PORTOES, ignorar_caixa=True):
        return "A", "caminho de portão"
    if casa_algum(caminho, GATILHOS_ADR, ignorar_caixa=True):
        return "A", "gatilho de ADR (N6)"
    if casa_algum(caminho, projeto.classe_a, ignorar_caixa=True):
        return "A", "caminho A do projeto"
    if casa_algum(caminho, C_PADRAO + projeto.classe_c):
        return "C", "documentação ou caminho C do projeto"
    return "B", "muda código fora dos caminhos A"


def _eh_teste(caminho: str) -> bool:
    return casa_algum(caminho, TESTES, ignorar_caixa=True)


def classificar_mudanca(m: Mudanca, projeto: Projeto) -> list[tuple[str, str, str]]:
    """Uma linha por caminho envolvido: o destino e, em rename ou cópia, também a origem."""
    linhas = [(m.caminho, *_classe_do_caminho(m.caminho, projeto))]
    if m.origem is not None:
        cls, motivo = _classe_do_caminho(m.origem, projeto)
        linhas.append((m.origem, cls, f"origem de {'rename' if m.status == 'R' else 'cópia'}: {motivo}"))
    if m.status == "D" and _eh_teste(m.caminho):
        linhas.append((m.caminho, "A", "remove arquivo de teste"))
    if m.status == "R" and m.origem is not None and _eh_teste(m.origem):
        linhas.append((m.origem, "A", "move arquivo de teste"))
    return linhas


def classificar(mudancas: list[Mudanca], projeto: Projeto) -> Resultado:
    motivos = tuple(sorted({linha for m in mudancas for linha in classificar_mudanca(m, projeto)}))
    if not motivos:
        return Resultado("C", ())
    classe = max((m[1] for m in motivos), key=ORDEM.__getitem__)
    return Resultado(classe, motivos)


def ler_name_status(saida: str) -> list[Mudanca]:
    """Interpreta a saída de `git diff --name-status -z`.

    Cada entrada é `STATUS\\0caminho\\0`, ou `RNNN\\0origem\\0destino\\0` em rename e cópia. Qualquer
    status fora do esperado é erro: o cálculo de classe falha fechado.
    """
    campos = saida.split("\0")
    if campos and campos[-1] == "":
        campos.pop()
    mudancas: list[Mudanca] = []
    i = 0
    while i < len(campos):
        status = campos[i][:1]
        if status in _STATUS_UM_CAMINHO and i + 1 < len(campos):
            mudancas.append(Mudanca(status, normalizar(campos[i + 1])))
            i += 2
        elif status in _STATUS_DOIS_CAMINHOS and i + 2 < len(campos):
            mudancas.append(Mudanca(status, normalizar(campos[i + 2]), origem=normalizar(campos[i + 1])))
            i += 3
        else:
            raise ErroClasse(f"saída do git diff inesperada perto de {campos[i]!r}")
    return mudancas


def mudancas_do_diff(raiz: Path, base: str) -> list[Mudanca]:
    """Mudanças desde o merge-base com `base` (o que o PR de fato traz), com rename detectado."""
    if base.startswith("-"):
        raise ErroClasse(f"ref base inválida: {base!r}")
    comando = [
        "git", "-C", str(raiz), "diff", "--name-status", "-z", "--find-renames", "--no-color", "--no-ext-diff",
        f"{base}...HEAD", "--",
    ]
    # surrogateescape: um nome de arquivo que não é UTF-8 não derruba o cálculo nem é trocado por outro.
    r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
                       check=False)
    if r.returncode != 0:
        raise ErroClasse(f"git diff falhou ({r.returncode}): {r.stderr.strip()}")
    return ler_name_status(r.stdout)


def efetiva(declarada: str | None, calculada: str) -> str:
    if declarada is None:
        return calculada
    return max(declarada, calculada, key=ORDEM.__getitem__)


def subiu(declarada: str | None, calculada: str) -> bool:
    """Verdadeiro quando o diff exige classe mais severa que a declarada no plano."""
    return declarada is not None and ORDEM[calculada] > ORDEM[declarada]
