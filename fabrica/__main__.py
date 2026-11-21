"""Linha de comando da fábrica.

    python -m fabrica sincronizar <projeto>
    python -m fabrica conferir <projeto>
    python -m fabrica classe <projeto> --base origin/main [--declarada B]
    python -m fabrica classe <projeto> --arquivos src/a.py docs/x.md [--declarada B]
    python -m fabrica autoria <repo> --intervalo BASE..HEAD --pessoa email [--pessoa email ...]
    python -m fabrica termos <repo> [--intervalo BASE..HEAD] [--evento $GITHUB_EVENT_PATH] [--texto-env NOME]
    python -m fabrica espelho conferir <repo>
    python -m fabrica espelho carimbar <repo> <arquivo.md> [...]
    python -m fabrica dossie conferir <dossie.json> [--portao]
    python -m fabrica dossie hash <dossie.json>
    python -m fabrica dossie renderizar <dossie.json>
    python -m fabrica preco simular <estimativa.toml> [--orcamento VALOR]
    python -m fabrica preco calibrar <historico.csv>
    python -m fabrica roteamento [--tokens N] [--autor FORNECEDOR] [--dado-pessoal] [--arquivo roteamento.toml]
    python -m fabrica contrato anthropic     # chamada real e mínima; precisa de ANTHROPIC_API_KEY

Em `classe`, <projeto> é a raiz do repositório. Com --arquivos, cada arquivo conta como modificado:
remoções e renames só aparecem com --base.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import autoria, classe, dossie, espelho, git, preco, projeto, roteamento, sincronizar, termos
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


def _autoria(a: argparse.Namespace) -> int:
    commits = autoria.ler_commits(a.repo, a.intervalo)
    violacoes = autoria.conferir(commits, a.pessoa)
    for v in violacoes:
        print(f"[N11] {v.sha}: {_mostravel(v.motivo)}")
    if violacoes:
        print(f"N11: {len(violacoes)} violação(ões) em {len(commits)} commit(s). Nenhum agente assina commit; "
              "quem escreveu o quê vai na descrição do PR.")
        return 1
    print(f"N11: OK em {len(commits)} commit(s)")
    return 0


def _termos(a: argparse.Namespace) -> int:
    lista = termos.carregar(os.environ.get(termos.VARIAVEL))
    achados = termos.conferir_arvore(a.repo, lista)
    if a.intervalo:
        achados += termos.conferir_commits(a.repo, a.intervalo, lista)
    if a.evento:
        achados += termos.conferir_evento(a.evento, lista)
    achados += termos.conferir_variaveis(a.texto_env or [], lista)
    for x in achados:
        lugar = f"{_mostravel(x.onde)}:{x.linha}" if x.linha else f"nome do arquivo {_mostravel(x.onde)}"
        print(f"[termo {x.termo}] {lugar}")
    if achados:
        print(f"Termos proibidos: {len(achados)} ocorrência(s). O termo não aparece aqui de propósito: "
              "o log é público. Consulte a lista pelo número.")
        return 1
    print(f"Termos proibidos: OK ({len(lista)} termo(s) conferido(s))")
    return 0


def _espelho(a: argparse.Namespace) -> int:
    if a.acao == "carimbar":
        if not a.arquivos:
            raise espelho.ErroEspelho("diga quais fontes carimbar, por exemplo: fabrica espelho carimbar . README.md")
        for fonte in a.arquivos:
            print(f"carimbado: {espelho.carimbar(a.repo, fonte)}")
        return 0
    r = espelho.conferir(a.repo)
    for rotulo, itens in (("sem tradução", r.faltando), ("desatualizado", r.desatualizados),
                          ("sem cabeçalho de origem", r.sem_cabecalho), ("órfão", r.orfaos)):
        for item in itens:
            print(f"[{rotulo}] {item}")
    if not r.limpo:
        print("Espelho en/: traduza ou atualize os arquivos acima e rode `fabrica espelho carimbar . <fonte>`.")
        return 1
    print("Espelho en/: OK")
    return 0


def _dossie(a: argparse.Namespace) -> int:
    d = dossie.ler(a.arquivo)
    r = dossie.conferir(d)
    if a.acao == "hash":
        if not r.valido:
            raise dossie.ErroDossie("dossiê inválido não tem hash de versão; rode `dossie conferir`")
        print(dossie.hash_canonico(d))
        return 0
    if a.acao == "renderizar":
        if not r.valido:
            raise dossie.ErroDossie("dossiê inválido não é renderizado; rode `dossie conferir`")
        print(dossie.renderizar(d, r), end="")
        return 0
    for erro in r.erros:
        print(f"[erro] {erro}")
    for bloqueio in r.bloqueios:
        print(f"[portão] {bloqueio}")
    if not r.valido:
        print(f"Dossiê inválido: {len(r.erros)} erro(s).")
        return 1
    print(f"Dossiê válido. {len(r.perguntas)} pergunta(s) aberta(s). "
          f"Portão {'aberto' if r.portao_aberto else 'fechado'}.")
    return 1 if a.portao and not r.portao_aberto else 0


def _numero(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _preco(a: argparse.Namespace) -> int:
    if a.acao == "calibrar":
        print("| Categoria | Itens | Cobertura do P80 | Real / provável (mediana) | Situação |")
        print("|---|---|---|---|---|")
        for c in preco.calibrar(a.arquivo):
            situacao = "usar a razão medida" if c.usar_razao else f"palpite (menos de {preco.MINIMO_CALIBRACAO} itens)"
            print(f"| {c.categoria} | {c.itens} | {c.cobertura_p80:.0%} | {_numero(c.razao_mediana, 2)} | {situacao} |")
        return 0
    modelo = preco.ler(a.arquivo)
    sim = preco.simular(modelo)
    horas, custo = preco.faixas(sim.horas()), preco.faixas(sim.custo())
    print(f"{modelo.rodadas} rodadas, semente {modelo.semente}, fator de projeto com sigma {modelo.sigma_fator}")
    print()
    print("| Faixa | Horas | Custo | Prazo (semanas) |")
    print("|---|---|---|---|")
    for p, rotulo in zip(preco.PERCENTIS, ("enxuto", "recomendado", "seguro"), strict=True):
        print(f"| P{p} ({rotulo}) | {_numero(horas[p])} | {modelo.moeda} {_numero(custo[p])} "
              f"| {_numero(horas[p] / modelo.horas_por_semana, 1)} |")
    print()
    print("Onde a incerteza mora (fração da variância das horas):")
    for nome, fracao in preco.contribuicoes(sim):
        print(f"- {nome}: {fracao:.0%}")
    if a.orcamento is not None:
        e = preco.escopo_para_orcamento(sim, a.orcamento)
        print()
        if not e.cabe:
            print(f"O essencial não cabe: P80 do essencial = {modelo.moeda} {_numero(e.p80)}, "
                  f"orçamento = {modelo.moeda} {_numero(a.orcamento)}.")
            return 1
        print(f"Com {modelo.moeda} {_numero(a.orcamento)}, entram com 80% de chance (P80 = {modelo.moeda} "
              f"{_numero(e.p80)}):")
        for nome in e.dentro:
            print(f"- {nome}")
        if e.fora:
            print("Ficam fora:")
            for nome in e.fora:
                print(f"- {nome}")
    return 0


def _roteamento(a: argparse.Namespace) -> int:
    r = roteamento.carregar(a.arquivo)
    print(f"Entrada de {a.tokens} tokens; autor: {a.autor or '-'}; dado pessoal de cliente: "
          f"{'sim' if a.dado_pessoal else 'não'}")
    for nome, papel in r.papeis.items():
        autor = a.autor or ("anthropic" if papel.revisor else None)
        e = roteamento.escolher(r, nome, roteamento.Tarefa(a.tokens, autor, a.dado_pessoal))
        ordem = [m.chave + (f" ({r.executor(m)})" if papel.agente else "") for m in e.candidatos]
        if e.humano_no_fim:
            ordem.append("humano")
        print(f"\n{nome}: {' -> '.join(ordem) or 'ninguém'}")
        for chave, motivo in e.pulados:
            print(f"  pulado {chave}: {motivo}")
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

    au = sub.add_parser("autoria", help="N11: falha se algum commit do intervalo tem agente como autor ou coautor")
    au.add_argument("repo", type=Path)
    au.add_argument("--intervalo", required=True, help="BASE..HEAD, por exemplo origin/main..HEAD")
    au.add_argument("--pessoa", action="append", required=True, help="e-mail de pessoa do projeto; repita")

    te = sub.add_parser("termos", help=f"falha se algum termo de ${termos.VARIAVEL} aparece no repositório")
    te.add_argument("repo", type=Path)
    te.add_argument("--intervalo", help="também confere as mensagens dos commits de BASE..HEAD")
    te.add_argument("--evento", type=Path, help="payload do evento do Actions; confere título e corpo do PR")
    te.add_argument("--texto-env", action="append", help="também confere o texto desta variável; repita")

    es = sub.add_parser("espelho", help="confere ou carimba as traduções em en/")
    es.add_argument("acao", choices=("conferir", "carimbar"))
    es.add_argument("repo", type=Path)
    es.add_argument("arquivos", nargs="*", help="fontes em português a carimbar (só com carimbar)")

    do = sub.add_parser("dossie", help="confere, identifica ou renderiza um dossiê de descoberta")
    do.add_argument("acao", choices=("conferir", "hash", "renderizar"))
    do.add_argument("arquivo", type=Path)
    do.add_argument("--portao", action="store_true", help="em conferir, falha também com o portão fechado")

    pr = sub.add_parser("preco", help="simula faixas de preço ou mede a calibração")
    pr.add_argument("acao", choices=("simular", "calibrar"))
    pr.add_argument("arquivo", type=Path, help="estimativa .toml (simular) ou histórico .csv (calibrar)")
    pr.add_argument("--orcamento", type=float, help="em simular, escolhe o escopo cujo P80 cabe neste valor")

    ro = sub.add_parser("roteamento", help="mostra, por papel, a ordem dos modelos e quem fica de fora")
    ro.add_argument("--arquivo", type=Path, default=roteamento.ARQUIVO)
    ro.add_argument("--tokens", type=int, default=10_000, help="entrada da chamada, em tokens")
    ro.add_argument("--autor", help="fornecedor do autor do PR (revisores); sem ele, vale anthropic")
    ro.add_argument("--dado-pessoal", action="store_true", help="projeto de cliente com dado pessoal")

    ct = sub.add_parser("contrato", help="chamada real e mínima à API do fornecedor (gasta menos de US$ 0,001)")
    ct.add_argument("fornecedor", choices=("anthropic",))

    a = ap.parse_args(argv)
    try:
        if a.comando == "sincronizar":
            escritos = sincronizar.sincronizar(a.projeto)
            print(f"{len(escritos)} arquivos em {a.projeto / sincronizar.PASTA}")
            return 0
        if a.comando == "classe":
            return _classe(a)
        if a.comando == "autoria":
            return _autoria(a)
        if a.comando == "termos":
            return _termos(a)
        if a.comando == "espelho":
            return _espelho(a)
        if a.comando == "dossie":
            return _dossie(a)
        if a.comando == "preco":
            return _preco(a)
        if a.comando == "roteamento":
            return _roteamento(a)
        if a.comando == "contrato":
            from . import contrato  # só aqui: o resto da linha de comando não depende dos clientes
            return contrato.anthropic()
        d = sincronizar.conferir(a.projeto)
        for rotulo, itens in (("alterado", d.alterados), ("faltando", d.faltando), ("sobrando", d.sobrando)):
            for item in itens:
                print(f"[{rotulo}] .fabrica/{item}")
        if not d.limpa:
            print("Deriva: .fabrica/ não pode ser editada à mão. Mude na fábrica e sincronize.")
            return 1
        print("OK: .fabrica/ igual à versão registrada")
        return 0
    except (projeto.ErroProjeto, sincronizar.ErroSincronizacao, classe.ErroClasse, git.ErroGit,
            termos.ErroTermos, espelho.ErroEspelho, dossie.ErroDossie, preco.ErroPreco, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
