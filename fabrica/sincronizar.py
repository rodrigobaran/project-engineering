"""Leva o conteúdo compartilhado da fábrica para `.fabrica/` de um projeto e confere a deriva.

O conteúdo mora uma vez só, aqui. Cada projeto recebe uma cópia fixada numa versão.
`.fabrica/versao` guarda o SHA da fábrica e o sha256 de cada arquivo copiado; `conferir`
falha se alguém editar, apagar ou acrescentar arquivo em `.fabrica/` à mão.
Só `.fabrica/projeto.toml` é do projeto e fica fora da conferência.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import projeto as proj

RAIZ_FABRICA = Path(__file__).resolve().parents[1]
PASTA = ".fabrica"
VERSAO = "versao"
EDITAVEIS = {"projeto.toml"}


class ErroSincronizacao(RuntimeError):
    pass


@dataclass(frozen=True)
class Deriva:
    alterados: tuple[str, ...]
    faltando: tuple[str, ...]
    sobrando: tuple[str, ...]

    @property
    def limpa(self) -> bool:
        return not (self.alterados or self.faltando or self.sobrando)


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def sha_da_fabrica(fabrica: Path = RAIZ_FABRICA) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=fabrica, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroSincronizacao("a fábrica precisa estar num repositório git com ao menos um commit")
    sujo = subprocess.run(["git", "status", "--porcelain"], cwd=fabrica, capture_output=True, text=True).stdout
    if sujo.strip():
        raise ErroSincronizacao("a fábrica tem mudanças não commitadas; sincronizar assim não é reproduzível")
    return r.stdout.strip()


def conteudo(camada: str, fabrica: Path = RAIZ_FABRICA) -> dict[str, Path]:
    """Mapa destino-relativo-a-.fabrica → arquivo de origem na fábrica."""
    origem_camada = fabrica / "camadas" / f"{camada}.md"
    if not origem_camada.is_file():
        disponiveis = sorted(p.stem for p in (fabrica / "camadas").glob("*.md"))
        raise ErroSincronizacao(f"camada '{camada}' não existe; disponíveis: {', '.join(disponiveis)}")
    mapa = {"camada.md": origem_camada}
    for arquivo in sorted((fabrica / "papeis").rglob("*")):
        if arquivo.is_file():
            mapa[f"papeis/{arquivo.relative_to(fabrica / 'papeis').as_posix()}"] = arquivo
    for arquivo in sorted((fabrica / "padrao").glob("*.md")):
        mapa[f"padrao/{arquivo.name}"] = arquivo
    return mapa


def sincronizar(destino: Path, sha: str | None = None, fabrica: Path = RAIZ_FABRICA) -> list[str]:
    """Copia o conteúdo para `destino/.fabrica/` e reescreve o manifesto. Devolve os arquivos escritos."""
    p = proj.ler(destino)
    sha = sha or sha_da_fabrica(fabrica)
    pasta = destino / PASTA
    mapa = conteudo(p.camada, fabrica)

    # Remove o que a fábrica deixou de fornecer, preservando o que é do projeto.
    for existente in sorted(pasta.rglob("*"), reverse=True):
        rel = existente.relative_to(pasta).as_posix()
        if existente.is_file() and rel not in mapa and rel not in EDITAVEIS and rel != VERSAO:
            existente.unlink()
        elif existente.is_dir() and not any(existente.iterdir()):
            existente.rmdir()

    for rel, origem in mapa.items():
        alvo = pasta / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, alvo)

    manifesto = {
        "fabrica": "rodrigobaran/project-engineering",
        "sha": sha,
        "camada": p.camada,
        "arquivos": {rel: _sha256(pasta / rel) for rel in sorted(mapa)},
    }
    (pasta / VERSAO).write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sorted(mapa)


def conferir(destino: Path) -> Deriva:
    pasta = destino / PASTA
    arquivo_versao = pasta / VERSAO
    if not arquivo_versao.is_file():
        raise ErroSincronizacao(f"{PASTA}/{VERSAO} não existe: rode a sincronização da fábrica")
    try:
        esperados: dict[str, str] = json.loads(arquivo_versao.read_text(encoding="utf-8"))["arquivos"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ErroSincronizacao(f"{PASTA}/{VERSAO} ilegível: {e}") from e

    presentes = {
        p.relative_to(pasta).as_posix()
        for p in pasta.rglob("*")
        if p.is_file() and p.relative_to(pasta).as_posix() not in EDITAVEIS | {VERSAO}
    }
    alterados = tuple(sorted(r for r in esperados if r in presentes and _sha256(pasta / r) != esperados[r]))
    faltando = tuple(sorted(set(esperados) - presentes))
    sobrando = tuple(sorted(presentes - set(esperados)))
    return Deriva(alterados, faltando, sobrando)
