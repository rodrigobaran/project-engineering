import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

from fabrica import chamada, custo, roteamento
from fabrica.__main__ import main
from fabrica.chamada import ErroTransitorio, Pedido, PrecisaHumano, Recusa, Resposta
from fabrica.custo import Livro, Registro, TetoAtingido, Tetos, Uso
from fabrica.roteamento import ErroRoteamento, Tarefa

ROTA = roteamento.carregar()
AGORA = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
TETOS = Tetos(Decimal(5), Decimal(20))
SCHEMA = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}


def _rota(texto_papeis: str, modelos: str | None = None) -> roteamento.Roteamento:
    modelos = modelos if modelos is not None else """
[modelos.a]
fornecedor = "anthropic"
id = "a"
contexto = 1000
preco = { entrada = 1, saida = 2 }
"""
    return roteamento.ler("limite_contexto = 0.7\nespera_padrao_s = 5\nespera_maxima_s = 60\n"
                          "[executores]\nanthropic = \"claude-code\"\n" + modelos + texto_papeis)


class ClienteFalso:
    """Devolve, por modelo, as respostas ou exceções da fila, na ordem, e anota cada chamada."""

    def __init__(self, roteiro: dict[str, list]):
        self.roteiro = {k: list(v) for k, v in roteiro.items()}
        self.chamadas: list[tuple[str, int]] = []

    def chamar(self, modelo, pedido, max_saida):
        self.chamadas.append((modelo.chave, max_saida))
        item = self.roteiro[modelo.chave].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.livro = Livro(Path(self.tmp.name) / "custo.jsonl")
        self.esperas: list[float] = []

    def pedido(self, papel="planejador", **kw):
        base = {"tarefa": "t1", "papel": papel, "sha": "abc123", "tokens_entrada": 10_000, "max_saida": 16_000,
                "conteudo": "prompt"}
        base.update(kw)
        return Pedido(**base)

    def chamar(self, pedido, cliente, rota=ROTA, tetos=TETOS):
        return chamada.chamar(pedido, rota, cliente, self.livro, tetos, agora=lambda: AGORA,
                              dormir=self.esperas.append, relogio=lambda: 0.0)

    def gasto_previo(self, valor: str, tarefa="t1", em=AGORA):
        self.livro.registrar(Registro(em.isoformat(), tarefa, "planejador", "anthropic", "opus-5-5", 1, "ok",
                                      0, 0, 0, Decimal(valor), 0.0, "sha"))

    def resultados(self):
        return [(r.modelo, r.resultado) for r in self.livro.registros()]


class TestArquivoDaFabrica(Base):
    def test_titulares_e_substitutos_batem_com_o_adr(self):
        esperado = {
            "triagem": ("haiku-5-5", "gemini-3-8-flash", "grok-4-3"),
            "planejador": ("fable-5-2", "opus-5-5", "grok-4-7"),
            "implementador_bc": ("sonnet-5-5", "gpt-6-2-sol", "humano"),
            "implementador_a": ("opus-5-5", "gpt-6-2-astra", "fable-5-2"),
            "revisor_de_claude": ("gemini-4-argon", "grok-4-7", "gpt-6-2-astra"),
            "revisor_de_outro": ("opus-5-5", "fable-5-2", "gemini-4-argon", "grok-4-7", "gpt-6-2-astra"),
            "revisor_seguranca": ("gemini-4-argon", "opus-5-5", "grok-4-7"),
        }
        self.assertEqual({nome: p.candidatos for nome, p in ROTA.papeis.items()}, esperado)

    def test_precos_conferidos_e_fable_marcado(self):
        self.assertEqual(ROTA.modelos["fable-5-2"].preco.entrada, Decimal("8.00"))
        self.assertEqual(ROTA.modelos["opus-5-5"].preco.saida, Decimal("20.00"))
        self.assertTrue(ROTA.modelos["fable-5-2"].sem_retencao_zero)
        self.assertEqual([k for k, m in ROTA.modelos.items() if m.sem_retencao_zero], ["fable-5-2"])

    def test_papel_de_agente_tem_executor_pelo_fornecedor(self):
        self.assertEqual(ROTA.executor(ROTA.modelos["sonnet-5-5"]), "claude-code")
        self.assertEqual(ROTA.executor(ROTA.modelos["gpt-6-2-sol"]), "codex")


class TestLeitura(unittest.TestCase):
    def test_float_do_toml_vira_decimal_exato(self):
        r = _rota('[papeis.p]\ncandidatos = ["a"]\n', """
[modelos.a]
fornecedor = "x"
id = "a"
contexto = 10
preco = { entrada = 0.10, saida = 0.30 }
""")
        self.assertEqual(r.modelos["a"].preco.entrada + r.modelos["a"].preco.saida, Decimal("0.40"))

    def test_erros_de_arquivo_falham_fechado(self):
        casos = {
            "candidato inexistente": '[papeis.p]\ncandidatos = ["b"]\n',
            "humano no meio": '[papeis.p]\ncandidatos = ["a", "humano", "a"]\n',
            "humano titular": '[papeis.p]\ncandidatos = ["humano"]\n',
            "campo desconhecido": '[papeis.p]\ncandidatos = ["a"]\nprioridade = 1\n',
            "repetido": '[papeis.p]\ncandidatos = ["a", "a"]\n',
        }
        for nome, texto in casos.items():
            with self.subTest(nome), self.assertRaises(ErroRoteamento):
                _rota(texto)

    def test_preco_negativo_ou_nao_finito_e_erro(self):
        for valor in ("-1", "nan", "inf"):
            with self.subTest(valor), self.assertRaises(ErroRoteamento):
                _rota('[papeis.p]\ncandidatos = ["a"]\n',
                      f'[modelos.a]\nfornecedor = "x"\nid = "a"\npreco = {{ entrada = {valor}, saida = 1 }}\n')

    def test_agente_sem_executor_para_o_fornecedor_e_erro(self):
        with self.assertRaises(ErroRoteamento):
            _rota('[papeis.p]\nagente = true\ncandidatos = ["a"]\n',
                  '[modelos.a]\nfornecedor = "google"\nid = "a"\n')


class TestEscolha(unittest.TestCase):
    def chaves(self, papel, **kw):
        e = roteamento.escolher(ROTA, papel, Tarefa(**{"tokens_entrada": 1000, **kw}))
        return [m.chave for m in e.candidatos], dict(e.pulados), e.humano_no_fim

    def test_revisor_pula_o_fornecedor_do_autor(self):
        ok, pulados, _ = self.chaves("revisor_seguranca", fornecedor_autor="anthropic")
        self.assertEqual(ok, ["gemini-4-argon", "grok-4-7"])
        self.assertIn("mesmo fornecedor", pulados["opus-5-5"])
        ok, _, _ = self.chaves("revisor_seguranca", fornecedor_autor="google")
        self.assertEqual(ok, ["opus-5-5", "grok-4-7"])

    def test_revisor_sem_autor_conhecido_e_erro(self):
        with self.assertRaises(ErroRoteamento):
            self.chaves("revisor_de_claude")

    def test_dado_pessoal_de_cliente_tira_o_fable_de_todas_as_linhas(self):
        ok, pulados, _ = self.chaves("planejador", dado_pessoal_cliente=True)
        self.assertEqual(ok[0], "opus-5-5")
        self.assertIn("retenção", pulados["fable-5-2"])
        ok, _, _ = self.chaves("revisor_de_outro", fornecedor_autor="openai", dado_pessoal_cliente=True)
        self.assertNotIn("fable-5-2", ok)
        self.assertEqual(self.chaves("planejador")[0][0], "fable-5-2")

    def test_acima_de_70_por_cento_do_contexto_pula_o_modelo(self):
        ok, pulados, _ = self.chaves("planejador", tokens_entrada=360_000)
        self.assertEqual(ok, ["fable-5-2", "opus-5-5"])
        self.assertIn("70%", pulados["grok-4-7"])
        ok, _, _ = self.chaves("planejador", tokens_entrada=350_000)  # exatamente 70% ainda cabe
        self.assertIn("grok-4-7", ok)

    def test_sem_preco_nunca_e_chamado(self):
        ok, pulados, _ = self.chaves("triagem")
        self.assertEqual(ok, ["haiku-5-5"])
        self.assertIn("sem preço", pulados["gemini-3-8-flash"])

    def test_humano_encerra_a_lista(self):
        ok, _, humano = self.chaves("implementador_bc")
        self.assertEqual(ok, ["sonnet-5-5"])
        self.assertTrue(humano)


class TestCusto(Base):
    def test_maximo_usa_a_saida_pedida_e_nao_a_esperada(self):
        opus = ROTA.modelos["opus-5-5"]
        # 10 mil de entrada a US$ 4 + 16 mil de saída a US$ 20, por milhão
        self.assertEqual(custo.custo_maximo(opus, 10_000, 16_000), Decimal("0.360000"))

    def test_saida_maxima_do_fable_sozinha_passa_do_teto_de_uma_tarefa(self):
        fable = ROTA.modelos["fable-5-2"]
        self.assertEqual(custo.custo_maximo(fable, 0, 128_000), Decimal("5.120000"))
        self.assertGreater(custo.custo_maximo(fable, 0, 128_000), TETOS.tarefa)

    def test_saida_pedida_acima_do_limite_do_modelo_e_cortada(self):
        argon = ROTA.modelos["gemini-4-argon"]
        self.assertEqual(custo.saida_efetiva(argon, 128_000), 65_000)

    def test_faixa_de_preco_pela_entrada(self):
        haiku = ROTA.modelos["haiku-5-5"]
        self.assertEqual(custo.custo_maximo(haiku, 100_000, 1), Decimal("0.010001"))  # 100 mil ainda na base
        self.assertEqual(custo.custo_maximo(haiku, 100_001, 1), Decimal("0.050003"))  # 0,50 e 2,50 acima

    def test_custo_real_com_cache(self):
        opus = ROTA.modelos["opus-5-5"]
        self.assertEqual(custo.custo_real(opus, Uso(entrada=1_000, saida=2_000, cache_leitura=10_000)),
                         Decimal("0.046000"))  # 0,004 + 0,040 + 0,002

    def test_arredonda_para_cima(self):
        haiku = ROTA.modelos["haiku-5-5"]
        self.assertEqual(custo.custo_real(haiku, Uso(1, 0)), Decimal("0.000001"))

    def test_teto_da_tarefa_e_do_dia(self):
        self.gasto_previo("4.80", tarefa="t1")
        self.gasto_previo("14.00", tarefa="t2")
        self.gasto_previo("100", tarefa="t3", em=AGORA - timedelta(days=1))  # ontem, em UTC: não conta
        custo.autorizar(self.livro, TETOS, "t1", AGORA.date(), Decimal("0.20"))
        with self.assertRaises(TetoAtingido):
            custo.autorizar(self.livro, TETOS, "t1", AGORA.date(), Decimal("0.21"))
        custo.autorizar(self.livro, TETOS, "t9", AGORA.date(), Decimal("1.20"))  # 4,80 + 14 + 1,20 = 20
        with self.assertRaisesRegex(TetoAtingido, "dia"):
            custo.autorizar(self.livro, TETOS, "t9", AGORA.date(), Decimal("1.21"))

    def test_linha_ilegivel_falha_fechado(self):
        self.gasto_previo("1")
        with self.livro.caminho.open("a", encoding="utf-8") as f:
            f.write("{nao e json\n")
        with self.assertRaises(custo.ErroCusto):
            self.livro.gastos("t1", AGORA.date())

    def test_registro_ida_e_volta(self):
        self.gasto_previo("0.123456")
        r = self.livro.registros()[0]
        self.assertEqual(r.custo_usd, Decimal("0.123456"))
        self.assertEqual(json.loads(self.livro.caminho.read_text())["custo_usd"], "0.123456")

    def test_tetos_do_ambiente(self):
        t = Tetos.do_ambiente({"ORQ_TETO_TAREFA_USD": "5", "ORQ_TETO_DIA_USD": "20"})
        self.assertEqual(t, Tetos(Decimal(5), Decimal(20)))
        for amb in ({}, {"ORQ_TETO_TAREFA_USD": "5"}, {"ORQ_TETO_TAREFA_USD": "x", "ORQ_TETO_DIA_USD": "1"},
                    {"ORQ_TETO_TAREFA_USD": "0", "ORQ_TETO_DIA_USD": "1"},
                    {"ORQ_TETO_TAREFA_USD": "NaN", "ORQ_TETO_DIA_USD": "1"}):
            with self.subTest(amb), self.assertRaises(custo.ErroCusto):
                Tetos.do_ambiente(amb)


class TestChamada(Base):
    def ok(self, saida=None):
        return Resposta({"ok": True} if saida is None else saida, Uso(1_000, 500))

    def test_sucesso_registra_custo_real(self):
        cliente = ClienteFalso({"fable-5-2": [self.ok()]})
        r = self.chamar(self.pedido(), cliente)
        self.assertEqual(r.modelo.chave, "fable-5-2")
        self.assertEqual(r.custo_usd, Decimal("0.028000"))  # 1000 x 8 + 500 x 40, por milhão
        self.assertEqual(self.resultados(), [("fable-5-2", "ok")])

    def test_teto_barra_antes_de_chamar_e_nao_troca_para_um_mais_barato(self):
        self.gasto_previo("4.50")
        cliente = ClienteFalso({"fable-5-2": [self.ok()], "opus-5-5": [self.ok()]})
        with self.assertRaises(TetoAtingido):
            self.chamar(self.pedido(), cliente)  # máximo do Fable: 0,08 + 0,64 = 0,72
        self.assertEqual(cliente.chamadas, [])
        self.assertEqual(self.resultados()[-1], ("fable-5-2", "bloqueada_teto"))

    def test_429_espera_o_retry_after_e_tenta_de_novo(self):
        cliente = ClienteFalso({"fable-5-2": [ErroTransitorio("429", retry_after=3), self.ok()]})
        self.chamar(self.pedido(), cliente)
        self.assertEqual(self.esperas, [3.0])
        self.assertEqual(self.resultados(), [("fable-5-2", "transitorio"), ("fable-5-2", "ok")])

    def test_sem_retry_after_usa_a_espera_padrao(self):
        cliente = ClienteFalso({"fable-5-2": [ErroTransitorio("503"), self.ok()]})
        self.chamar(self.pedido(), cliente)
        self.assertEqual(self.esperas, [5.0])

    def test_segunda_falha_passa_ao_substituto_e_registra_a_troca(self):
        cliente = ClienteFalso({"fable-5-2": [ErroTransitorio("529"), ErroTransitorio("529")],
                                "opus-5-5": [self.ok()]})
        r = self.chamar(self.pedido(), cliente)
        self.assertEqual(r.modelo.chave, "opus-5-5")
        self.assertEqual(self.resultados(), [("fable-5-2", "transitorio"), ("fable-5-2", "transitorio"),
                                             ("fable-5-2", "troca"), ("opus-5-5", "ok")])
        self.assertIn("fable-5-2 -> opus-5-5", self.livro.registros()[2].detalhe)

    def test_retry_after_longo_vai_direto_ao_substituto(self):
        cliente = ClienteFalso({"fable-5-2": [ErroTransitorio("429", retry_after=3600)], "opus-5-5": [self.ok()]})
        r = self.chamar(self.pedido(), cliente)
        self.assertEqual(r.modelo.chave, "opus-5-5")
        self.assertEqual(self.esperas, [])
        self.assertEqual(cliente.chamadas[0][0], "fable-5-2")
        self.assertEqual(len(cliente.chamadas), 2)

    def test_recusa_cobrada_entra_no_gasto(self):
        cliente = ClienteFalso({"fable-5-2": [Recusa("cyber", Uso(1_000, 0)), self.ok()]})
        self.chamar(self.pedido(), cliente)
        recusa = self.livro.registros()[0]
        self.assertEqual((recusa.resultado, recusa.custo_usd), ("recusa", Decimal("0.008000")))

    def test_saida_fora_do_schema_nunca_e_consertada(self):
        ruim = Resposta({"ok": "sim"}, Uso(1_000, 500))
        cliente = ClienteFalso({"fable-5-2": [ruim, ruim], "opus-5-5": [self.ok()]})
        r = self.chamar(self.pedido(schema=SCHEMA), cliente)
        self.assertEqual((r.modelo.chave, r.saida), ("opus-5-5", {"ok": True}))
        invalidas = [x for x in self.livro.registros() if x.resultado == "saida_invalida"]
        self.assertEqual(len(invalidas), 2)
        self.assertTrue(all(x.custo_usd > 0 for x in invalidas))  # a saída ruim também foi paga

    def test_erro_definitivo_para_sem_trocar(self):
        cliente = ClienteFalso({"fable-5-2": [PermissionError("401: chave inválida")], "opus-5-5": [self.ok()]})
        with self.assertRaises(PermissionError):
            self.chamar(self.pedido(), cliente)
        self.assertEqual([c[0] for c in cliente.chamadas], ["fable-5-2"])
        self.assertEqual(self.resultados(), [("fable-5-2", "erro")])

    def test_ninguem_atende_precisa_humano_com_o_motivo_de_cada_um(self):
        falha = [ErroTransitorio("529"), ErroTransitorio("529")]
        cliente = ClienteFalso({"haiku-5-5": list(falha)})
        with self.assertRaises(PrecisaHumano) as ctx:
            self.chamar(self.pedido("triagem"), cliente)
        motivos = " | ".join(ctx.exception.motivos)
        self.assertIn("gemini-3-8-flash: sem preço", motivos)
        self.assertIn("haiku-5-5: erro transitório", motivos)

    def test_custo_real_acima_do_maximo_para_tudo(self):
        enorme = Resposta({"ok": True}, Uso(100_000, 500))  # declarou 10 mil de entrada; veio 100 mil
        cliente = ClienteFalso({"fable-5-2": [enorme], "opus-5-5": [self.ok()]})
        with self.assertRaisesRegex(custo.ErroCusto, "acima do máximo"):
            self.chamar(self.pedido(), cliente)
        self.assertEqual(len(cliente.chamadas), 1)
        ultimo = self.livro.registros()[-1]
        self.assertEqual((ultimo.resultado, ultimo.custo_usd), ("acima_do_maximo", Decimal("0.820000")))

    def test_papel_de_agente_nao_e_chamada_direta(self):
        with self.assertRaises(ErroRoteamento):
            self.chamar(self.pedido("implementador_a"), ClienteFalso({}))

    def test_cada_linha_do_log_tem_os_campos_do_adr(self):
        self.chamar(self.pedido(), ClienteFalso({"fable-5-2": [self.ok()]}))
        linha = json.loads(self.livro.caminho.read_text(encoding="utf-8").splitlines()[0])
        for campo in ("papel", "fornecedor", "modelo", "entrada", "saida", "cache_leitura", "custo_usd",
                      "duracao_s", "tarefa", "sha", "resultado"):
            self.assertIn(campo, linha)
        self.assertEqual(date.fromisoformat(linha["em"][:10]), AGORA.date())


class TestLinhaDeComando(unittest.TestCase):
    def test_roteamento_mostra_ordem_e_motivos(self):
        saida = StringIO()
        with redirect_stdout(saida):
            self.assertEqual(main(["roteamento", "--dado-pessoal"]), 0)
        texto = saida.getvalue()
        self.assertIn("planejador: opus-5-5 -> grok-4-7", texto)
        self.assertIn("pulado fable-5-2: exige retenção", texto)
        self.assertIn("implementador_bc: sonnet-5-5 (claude-code) -> humano", texto)


if __name__ == "__main__":
    unittest.main()
