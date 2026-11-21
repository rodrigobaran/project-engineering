"""Contrato com a API de verdade: uma chamada mínima por fornecedor, pelo mesmo caminho do orquestrador.

As respostas de teste em `tests/respostas/` foram montadas a partir da documentação. Este contrato confere que
a API ainda responde no formato que elas supõem: contagem, streaming, saída estruturada, uso e custo. Roda só
à mão (workflow `contrato`), com a chave no ambiente. Os tetos são fixos e pequenos (US$ 0,01), e a chamada
custa menos de US$ 0,001.
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from . import chamada, roteamento
from .anthropic import ClienteAnthropic, ErroFornecedor
from .custo import Livro, Tetos
from .transporte import Transporte

TETO_USD = Decimal("0.01")
SCHEMA = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}


def anthropic(ambiente: Mapping[str, str] | None = None, transporte: Transporte | None = None) -> int:
    ambiente = os.environ if ambiente is None else ambiente
    rota = roteamento.carregar()
    try:
        cliente = ClienteAnthropic.do_ambiente(ambiente, transporte)
    except ErroFornecedor as e:
        print(f"contrato anthropic: FALHOU: {e}", file=sys.stderr)
        return 1
    pedido = chamada.Pedido(
        tarefa="contrato-anthropic", papel="triagem", sha=ambiente.get("GITHUB_SHA", "local"),
        tokens_entrada=100, max_saida=1024, esforco="low", schema=SCHEMA,
        conteudo=chamada.Prompt("Responda só com o JSON pedido.", 'Responda exatamente {"ok": true}.'))
    with tempfile.TemporaryDirectory() as pasta:
        livro = Livro(Path(pasta) / "custo.jsonl")
        try:
            r = chamada.chamar(pedido, rota, cliente, livro, Tetos(TETO_USD, TETO_USD))
        except Exception as e:  # qualquer falha reprova o contrato, com o tipo e o motivo
            falha: Exception | None = e
        else:
            falha = None
        for registro in livro.registros():
            print(f"{registro.modelo} tentativa {registro.tentativa}: {registro.resultado}; "
                  f"entrada {registro.entrada}, saída {registro.saida}, cache {registro.cache_leitura}; "
                  f"US$ {registro.custo_usd}; {registro.duracao_s} s {registro.detalhe}".rstrip())
    if falha is not None:
        print(f"contrato anthropic: FALHOU: {type(falha).__name__}: {falha}", file=sys.stderr)
        return 1
    print(f"contrato anthropic: OK com {r.modelo.id}, saída {r.saida}, US$ {r.custo_usd}")
    return 0
