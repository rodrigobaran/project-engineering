import math
import random
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from fabrica import preco
from fabrica.__main__ import main

RAIZ = Path(__file__).resolve().parent.parent


def modelo(itens, sigma=0.0, custos=(), riscos=None, rodadas=4000, taxa=100):
    return preco.montar({"taxa_hora": taxa, "horas_por_semana": 40, "rodadas": rodadas, "semente": 3,
                         "fator_projeto": {"sigma": sigma}, "riscos": riscos or {}, "itens": list(itens),
                         "custos": list(custos)})


def item(nome, horas, prioridade="essencial", riscos=()):
    return {"nome": nome, "prioridade": prioridade, "horas": list(horas), "riscos": list(riscos)}


class TestEntrada(unittest.TestCase):
    def test_tres_pontos_fora_de_ordem(self):
        with self.assertRaises(preco.ErroPreco):
            modelo([item("a", [10, 5, 20])])

    def test_risco_sem_peso_declarado(self):
        with self.assertRaises(preco.ErroPreco):
            modelo([item("a", [1, 2, 3], riscos=["dinheiro"])])

    def test_prioridade_invalida(self):
        with self.assertRaises(preco.ErroPreco):
            modelo([item("a", [1, 2, 3], prioridade="urgente")])

    def test_poucas_rodadas(self):
        with self.assertRaises(preco.ErroPreco):
            modelo([item("a", [1, 2, 3])], rodadas=10)

    def test_risco_alarga_o_pessimista_e_nao_o_provavel(self):
        m = modelo([item("a", [8, 10, 20], riscos=["dinheiro", "pergunta_aberta"])],
                   riscos={"dinheiro": 0.3, "pergunta_aberta": 0.5})
        a = m.itens[0]
        self.assertEqual((a.otimista, a.provavel), (8, 10))
        self.assertTrue(math.isclose(a.pessimista, 10 + 10 * 1.8))


class TestSimulacao(unittest.TestCase):
    def test_pontos_iguais_e_sem_fator_dao_valor_fixo(self):
        sim = preco.simular(modelo([item("a", [10, 10, 10]), item("b", [5, 5, 5])],
                                   custos=[{"nome": "c", "valor": [50, 50, 50]}]))
        self.assertEqual(set(preco.faixas(sim.horas()).values()), {15})
        self.assertEqual(set(preco.faixas(sim.custo()).values()), {1550})

    def test_faixas_em_ordem(self):
        sim = preco.simular(modelo([item("a", [5, 10, 30]), item("b", [2, 4, 12])], sigma=0.2))
        f = preco.faixas(sim.custo())
        self.assertLess(f[50], f[80])
        self.assertLess(f[80], f[95])

    def test_mesma_semente_mesmo_resultado(self):
        m = modelo([item("a", [5, 10, 30])], sigma=0.2)
        self.assertEqual(preco.simular(m).custo(), preco.simular(m).custo())

    def test_pert_fica_dentro_dos_limites_e_perto_da_media_teorica(self):
        rng = random.Random(1)  # noqa: S311 - simulação, não criptografia
        amostras = [preco.sortear_pert(rng, 10, 20, 60) for _ in range(20000)]
        self.assertTrue(all(10 <= x <= 60 for x in amostras))
        media_pert = (10 + 4 * 20 + 60) / 6
        self.assertAlmostEqual(sum(amostras) / len(amostras), media_pert, delta=0.5)

    def test_fator_de_projeto_engorda_a_cauda(self):
        # O erro clássico: itens independentes se cancelam e a cauda some.
        itens = [item(f"i{n}", [8, 10, 16]) for n in range(10)]
        independente = preco.faixas(preco.simular(modelo(itens, sigma=0.0)).horas())
        correlacionado = preco.faixas(preco.simular(modelo(itens, sigma=0.25)).horas())
        self.assertGreater(correlacionado[95] - correlacionado[50], 2 * (independente[95] - independente[50]))

    def test_custo_que_acompanha_o_fator(self):
        fixo = {"nome": "infra", "valor": [100, 100, 100]}
        tokens = {"nome": "tokens", "valor": [100, 100, 100], "acompanha_fator": True}
        sim_fixo = preco.simular(modelo([item("a", [0, 0, 0])], sigma=0.3, custos=[fixo]))
        sim_tokens = preco.simular(modelo([item("a", [0, 0, 0])], sigma=0.3, custos=[tokens]))
        self.assertEqual(set(sim_fixo.custos_extras), {100})
        self.assertGreater(len(set(sim_tokens.custos_extras)), 100)

    def test_contribuicoes_somam_um_e_apontam_o_item_mais_incerto(self):
        sim = preco.simular(modelo([item("estreito", [9, 10, 11]), item("largo", [5, 10, 60])], sigma=0.1))
        contrib = preco.contribuicoes(sim)
        self.assertAlmostEqual(sum(f for _, f in contrib), 1.0, places=6)
        self.assertEqual(contrib[0][0], "largo")


class TestEscopo(unittest.TestCase):
    def sim(self):
        return preco.simular(modelo([
            item("base", [10, 10, 10]),
            item("importante caro", [30, 30, 30], "importante"),
            item("importante barato", [5, 5, 5], "importante"),
            item("desejavel", [8, 8, 8], "desejavel"),
        ]))

    def test_orcamento_folgado_leva_tudo(self):
        e = preco.escopo_para_orcamento(self.sim(), 10_000)
        self.assertEqual((len(e.dentro), e.fora), (4, ()))

    def test_essencial_que_nao_cabe(self):
        e = preco.escopo_para_orcamento(self.sim(), 500)
        self.assertFalse(e.cabe)
        self.assertEqual(e.p80, 1000)

    def test_prioridade_e_depois_o_mais_barato(self):
        # 2.300 = base (1.000) + importante barato (500) + desejável (800); o importante caro não cabe.
        e = preco.escopo_para_orcamento(self.sim(), 2300)
        self.assertEqual(set(e.dentro), {"base", "importante barato", "desejavel"})
        self.assertEqual(e.fora, ("importante caro",))
        self.assertEqual(e.p80, 2300)


    def test_mais_barato_primeiro_leva_mais_itens(self):
        # Orçamento 4.000: o caro sozinho cabe (1.000 + 3.000), mas os dois baratos juntos são mais escopo.
        sim = preco.simular(modelo([
            item("base", [10, 10, 10]),
            item("caro", [30, 30, 30], "importante"),
            item("barato 1", [12, 12, 12], "importante"),
            item("barato 2", [12, 12, 12], "importante"),
        ]))
        e = preco.escopo_para_orcamento(sim, 4000)
        self.assertEqual(set(e.dentro), {"base", "barato 1", "barato 2"})


class TestCalibracao(unittest.TestCase):
    def escrever(self, linhas):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
            f.write("item,categoria,otimista,provavel,pessimista,real\n" + "".join(linhas))
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_cobertura_e_limite_de_itens(self):
        dentro = [f"a{n},fluxo,8,10,20,10\n" for n in range(8)]
        estouro = [f"b{n},fluxo,8,10,20,40\n" for n in range(2)]
        poucos = ["c,integracao,8,10,20,10\n"]
        r = {c.categoria: c for c in preco.calibrar(self.escrever(dentro + estouro + poucos), rodadas=2000)}
        self.assertAlmostEqual(r["fluxo"].cobertura_p80, 0.8)
        self.assertTrue(r["fluxo"].usar_razao)
        self.assertFalse(r["integracao"].usar_razao)
        self.assertEqual(r["fluxo"].razao_mediana, 1.0)

    def test_linha_invalida(self):
        with self.assertRaises(preco.ErroPreco):
            preco.calibrar(self.escrever(["a,fluxo,8,x,20,10\n"]))


class TestCliPreco(unittest.TestCase):
    def rodar(self, *args):
        with redirect_stdout(StringIO()) as saida, redirect_stderr(StringIO()):
            codigo = main(["preco", *args])
        return codigo, saida.getvalue()

    def test_exemplo_publico(self):
        codigo, saida = self.rodar("simular", str(RAIZ / "precificacao" / "exemplo.toml"), "--orcamento", "25000")
        self.assertEqual(codigo, 0, saida)
        self.assertIn("| P80 (recomendado) |", saida)
        self.assertIn("Onde a incerteza mora", saida)

    def test_orcamento_abaixo_do_essencial(self):
        codigo, saida = self.rodar("simular", str(RAIZ / "precificacao" / "exemplo.toml"), "--orcamento", "1000")
        self.assertEqual(codigo, 1)
        self.assertIn("O essencial não cabe", saida)

    def test_calibrar_exemplo(self):
        codigo, saida = self.rodar("calibrar", str(RAIZ / "precificacao" / "historico-exemplo.csv"))
        self.assertEqual(codigo, 0)
        self.assertIn("| fluxo | 12 |", saida)


if __name__ == "__main__":
    unittest.main()
