"""Dossiê de descoberta: a entrada única do planejador, com o backend primeiro.

O schema (`descoberta/schema.json`) confere a forma. Este módulo confere o que depende do conteúdo:

- Cada seção termina em um de três estados: `respondida` (com afirmações), `nao_se_aplica` (com motivo)
  ou `pergunta_aberta` (com perguntas que têm dono e prazo). Seção em branco não existe.
- Toda afirmação e todo cenário citam uma fonte declarada, ou se marcam como hipótese. Nunca as duas
  coisas, e nunca nenhuma.
- Fluxo crítico respondido tem ao menos um cenário "dado, quando, então": é dele que sai o teste de aceite.

Portão da descoberta: o planejamento só começa sem pergunta aberta e sem hipótese no núcleo do backend
(atores e permissões, modelo de domínio, ciclos de vida, dados pessoais e dinheiro). Hipótese no núcleo
é uma pergunta que ninguém fez.

A seção 14 (perguntas abertas) não é escrita à mão: é a soma das perguntas das outras seções, para não
existirem duas listas que divergem.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import esquema

SCHEMA = Path(__file__).resolve().parent.parent / "descoberta" / "schema.json"

# (chave, título, pergunta que a seção responde, saída verificável)
SECOES = (
    ("objetivo", "Objetivo", "Por que o sistema existe e como saber se deu certo", "1 a 3 métricas com número"),
    ("atores_permissoes", "Atores e permissões", "Quem pode fazer o quê, em quais dados",
     "Matriz papel × ação × recurso"),
    ("modelo_dominio", "Modelo de domínio", "Entidades, relações e o que nunca pode ser falso",
     "Diagrama e lista de invariantes"),
    ("ciclos_de_vida", "Ciclos de vida", "Por quais estados cada entidade passa", "Máquina de estados por entidade"),
    ("fluxos_criticos", "Fluxos críticos", "O que não pode quebrar", "Cenários \"dado, quando, então\""),
    ("dados_pessoais", "Dados pessoais", "Quais dados, base legal, retenção, direitos do titular",
     "Inventário de dados"),
    ("dinheiro", "Dinheiro", "Moeda, arredondamento, repetição segura, conciliação",
     "Regras e casos de teste com valores"),
    ("integracoes", "Integrações", "Com quem o sistema conversa e o que acontece quando o outro lado cai",
     "Lista com contrato, limite e modo de falha"),
    ("volume_desempenho", "Volume e desempenho", "Quantos usuários, quantas operações, que espera é aceitável",
     "Números com faixa"),
    ("auditoria", "Auditoria", "Quem precisa saber o que mudou, quando e por quem", "Lista de eventos auditáveis"),
    ("ameacas", "Ameaças", "Como cada fluxo crítico pode ser atacado", "Ameaças STRIDE com mitigação e teste"),
    ("operacao", "Operação", "Backup, recuperação, monitoramento, publicação", "Metas de RPO e RTO"),
    ("fora_de_escopo", "Fora de escopo", "O que não será feito", "Lista explícita"),
)
NUCLEO_BACKEND = ("atores_permissoes", "modelo_dominio", "ciclos_de_vida", "dados_pessoais", "dinheiro")


class ErroDossie(ValueError):
    pass


@dataclass
class Resultado:
    erros: list[str] = field(default_factory=list)
    bloqueios: list[str] = field(default_factory=list)  # o que fecha o portão
    perguntas: list[tuple[str, dict]] = field(default_factory=list)  # (seção, pergunta)

    @property
    def valido(self) -> bool:
        return not self.erros

    @property
    def portao_aberto(self) -> bool:
        return self.valido and not self.bloqueios


def ler(caminho: Path) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ErroDossie(f"não consegui ler {caminho}: {e}") from e


def hash_canonico(dossie: Any) -> str:
    """sha256 do JSON canônico (chaves ordenadas, sem espaços, UTF-8). Identifica a versão aprovada."""
    texto = json.dumps(dossie, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _citacoes(item: dict, onde: str, fontes: set[str], erros: list[str]) -> bool:
    """Confere fonte ou hipótese. Devolve True quando o item é hipótese."""
    citacoes = item.get("fontes", [])
    hipotese = item.get("hipotese", False)
    if citacoes and hipotese:
        erros.append(f"{onde}: tem fonte e está marcado como hipótese; escolha um")
    elif not citacoes and not hipotese:
        erros.append(f"{onde}: sem fonte; cite a fonte ou marque como hipótese")
    for c in citacoes:
        if c["fonte"] not in fontes:
            erros.append(f"{onde}: cita a fonte {c['fonte']}, que não está em 'fontes'")
    return bool(hipotese)


def conferir(dossie: Any, schema: dict | None = None) -> Resultado:
    r = Resultado()
    schema = schema if schema is not None else json.loads(SCHEMA.read_text(encoding="utf-8"))
    r.erros = esquema.validar(dossie, schema)
    if r.erros:
        return r  # a forma está errada; as regras abaixo supõem a forma certa

    ids = [f["id"] for f in dossie["fontes"]]
    fontes = set(ids)
    if len(ids) != len(fontes):
        r.erros.append("fontes: id repetido")
    for chave, titulo, _, _ in SECOES:
        s = dossie["secoes"][chave]
        estado = s["estado"]
        onde = f"{chave}"
        afirmacoes, cenarios, perguntas = s.get("afirmacoes", []), s.get("cenarios", []), s.get("perguntas", [])
        if estado == "respondida" and not (afirmacoes or cenarios):
            r.erros.append(f"{onde}: respondida sem nenhuma afirmação")
        if estado == "respondida" and perguntas:
            r.erros.append(f"{onde}: respondida com pergunta pendente; use pergunta_aberta")
        if estado == "nao_se_aplica":
            if "motivo" not in s:
                r.erros.append(f"{onde}: não se aplica sem motivo escrito")
            if afirmacoes or cenarios or perguntas:
                r.erros.append(f"{onde}: não se aplica, mas tem conteúdo; escolha um estado")
        elif "motivo" in s:
            r.erros.append(f"{onde}: 'motivo' só vale em nao_se_aplica")
        if estado == "pergunta_aberta" and not perguntas:
            r.erros.append(f"{onde}: pergunta_aberta sem nenhuma pergunta")
        if chave == "fluxos_criticos" and estado == "respondida" and not cenarios:
            r.erros.append(f"{onde}: fluxo crítico respondido sem cenário \"dado, quando, então\"")
        if chave != "fluxos_criticos" and cenarios:
            r.erros.append(f"{onde}: cenários só valem em fluxos_criticos")

        hipoteses = 0
        for i, a in enumerate(afirmacoes):
            hipoteses += _citacoes(a, f"{onde}.afirmacoes[{i}]", fontes, r.erros)
        for i, c in enumerate(cenarios):
            hipoteses += _citacoes(c, f"{onde}.cenarios[{i}]", fontes, r.erros)
        r.perguntas.extend((titulo, p) for p in perguntas)

        if chave in NUCLEO_BACKEND:
            if estado == "pergunta_aberta":
                r.bloqueios.append(f"{titulo}: {len(perguntas)} pergunta(s) aberta(s) no núcleo do backend")
            if hipoteses:
                r.bloqueios.append(f"{titulo}: {hipoteses} hipótese(s) no núcleo do backend")
    return r


def _cita(item: dict) -> str:
    if item.get("hipotese"):
        return " *(hipótese)*"
    return " " + "; ".join(f"[{c['fonte']}: {c['trecho']}]" for c in item.get("fontes", []))


def renderizar(dossie: Any, resultado: Resultado) -> str:
    """Markdown para o cliente e para o anexo do contrato. Supõe um dossiê válido."""
    linhas = [
        f"# Dossiê de descoberta: {dossie['projeto']}",
        "",
        f"Versão {dossie['versao']} · {dossie['data']} · sha256 `{hash_canonico(dossie)}`",
        "",
        "Portão: **aberto**" if resultado.portao_aberto else "Portão: **fechado**",
    ]
    linhas += [f"- {b}" for b in resultado.bloqueios]
    linhas += ["", "## Fontes", "", "| Id | Tipo | Descrição |", "|---|---|---|"]
    linhas += [f"| {f['id']} | {f['tipo']} | {f['descricao']} |" for f in dossie["fontes"]]
    rotulos = {"respondida": "respondida", "nao_se_aplica": "não se aplica", "pergunta_aberta": "pergunta aberta"}
    for n, (chave, titulo, pergunta, saida) in enumerate(SECOES, start=1):
        s = dossie["secoes"][chave]
        linhas += ["", f"## {n}. {titulo}", "", f"*{pergunta}. Saída: {saida}.* Estado: {rotulos[s['estado']]}.", ""]
        if "motivo" in s:
            linhas.append(f"Não se aplica porque {s['motivo']}")
        linhas += [f"- {a['texto']}{_cita(a)}" for a in s.get("afirmacoes", [])]
        for c in s.get("cenarios", []):
            linhas += [f"- **{c['nome']}.** Dado {c['dado']}; quando {c['quando']}; então {c['entao']}.{_cita(c)}"]
        for p in s.get("perguntas", []):
            linhas.append(f"- Pergunta: {p['pergunta']} (dono: {p['dono']}, prazo: {p['prazo']})")
    linhas += ["", f"## {len(SECOES) + 1}. Perguntas abertas", ""]
    if resultado.perguntas:
        linhas += ["| Seção | Pergunta | Dono | Prazo |", "|---|---|---|---|"]
        linhas += [f"| {sec} | {p['pergunta']} | {p['dono']} | {p['prazo']} |" for sec, p in resultado.perguntas]
    else:
        linhas.append("Nenhuma.")
    return "\n".join(linhas) + "\n"
