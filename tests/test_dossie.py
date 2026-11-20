import copy
import glob
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from fabrica import dossie, esquema
from fabrica.__main__ import main

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLO = json.loads((RAIZ / "descoberta" / "exemplo.json").read_text(encoding="utf-8"))


class TestEsquema(unittest.TestCase):
    def test_schemas_da_fabrica_usam_so_o_subconjunto_suportado(self):
        arquivos = glob.glob(str(RAIZ / "papeis" / "schemas" / "*.json")) + [str(dossie.SCHEMA)]
        self.assertGreaterEqual(len(arquivos), 4)
        for arquivo in arquivos:
            esquema.conferir_schema(json.loads(Path(arquivo).read_text(encoding="utf-8")))

    def test_palavra_desconhecida_e_erro_nao_silencio(self):
        with self.assertRaises(esquema.ErroSchema):
            esquema.validar(1, {"type": "integer", "maximum": 3})

    def test_tipos_e_restricoes(self):
        s = {"type": "object", "additionalProperties": False, "required": ["a"],
             "properties": {"a": {"type": "integer"}, "b": {"type": "array", "minItems": 1,
                                                            "items": {"type": "string", "pattern": "^x"}}}}
        self.assertEqual(esquema.validar({"a": 1, "b": ["xy"]}, s), [])
        erros = esquema.validar({"a": True, "b": ["y"], "c": 0}, s)
        self.assertEqual(len(erros), 3, erros)  # booleano não é inteiro; padrão; campo extra
        self.assertIn("$: falta 'a'", esquema.validar({}, s))

    def test_ref_local(self):
        s = {"$defs": {"d": {"enum": ["x"]}}, "type": "array", "items": {"$ref": "#/$defs/d"}}
        self.assertEqual(esquema.validar(["x"], s), [])
        self.assertEqual(len(esquema.validar(["y"], s)), 1)


class TestDossie(unittest.TestCase):
    def d(self):
        return copy.deepcopy(EXEMPLO)

    def test_exemplo_e_valido_e_abre_o_portao(self):
        r = dossie.conferir(self.d())
        self.assertEqual((r.erros, r.bloqueios), ([], []))
        self.assertEqual(len(r.perguntas), 1)  # integrações: fora do núcleo, não bloqueia

    def test_falta_secao(self):
        d = self.d()
        del d["secoes"]["dinheiro"]
        self.assertIn("$.secoes: falta 'dinheiro'", dossie.conferir(d).erros)

    def test_afirmacao_sem_fonte_e_sem_hipotese(self):
        d = self.d()
        del d["secoes"]["objetivo"]["afirmacoes"][0]["fontes"]
        self.assertTrue(any("sem fonte" in e for e in dossie.conferir(d).erros))

    def test_fonte_inexistente(self):
        d = self.d()
        d["secoes"]["objetivo"]["afirmacoes"][0]["fontes"][0]["fonte"] = "F9"
        self.assertTrue(any("F9" in e for e in dossie.conferir(d).erros))

    def test_fonte_e_hipotese_ao_mesmo_tempo(self):
        d = self.d()
        d["secoes"]["objetivo"]["afirmacoes"][0]["hipotese"] = True
        self.assertTrue(any("escolha um" in e for e in dossie.conferir(d).erros))

    def test_nao_se_aplica_exige_motivo_e_nada_mais(self):
        d = self.d()
        d["secoes"]["dinheiro"] = {"estado": "nao_se_aplica"}
        self.assertTrue(any("sem motivo" in e for e in dossie.conferir(d).erros))
        d["secoes"]["dinheiro"] = {"estado": "nao_se_aplica", "motivo": "o sistema não cobra nada."}
        self.assertTrue(dossie.conferir(d).valido)

    def test_pergunta_aberta_exige_pergunta_com_dono_e_prazo(self):
        d = self.d()
        d["secoes"]["auditoria"] = {"estado": "pergunta_aberta", "perguntas": []}
        self.assertTrue(any("sem nenhuma pergunta" in e for e in dossie.conferir(d).erros))
        d["secoes"]["auditoria"] = {"estado": "pergunta_aberta", "perguntas": [{"pergunta": "x", "dono": "y"}]}
        self.assertTrue(any("falta 'prazo'" in e for e in dossie.conferir(d).erros))

    def test_respondida_com_pergunta_pendente_e_erro(self):
        d = self.d()
        d["secoes"]["objetivo"]["perguntas"] = [{"pergunta": "x", "dono": "y", "prazo": "2026-12-01"}]
        self.assertTrue(any("use pergunta_aberta" in e for e in dossie.conferir(d).erros))

    def test_fluxo_critico_sem_cenario(self):
        d = self.d()
        d["secoes"]["fluxos_criticos"] = {"estado": "respondida",
                                          "afirmacoes": [{"texto": "x", "hipotese": True}]}
        self.assertTrue(any("sem cenário" in e for e in dossie.conferir(d).erros))

    def test_pergunta_no_nucleo_fecha_o_portao(self):
        d = self.d()
        d["secoes"]["dinheiro"] = {"estado": "pergunta_aberta",
                                   "perguntas": [{"pergunta": "Aceita parcelamento?", "dono": "cliente",
                                                  "prazo": "2026-12-01"}]}
        r = dossie.conferir(d)
        self.assertTrue(r.valido)
        self.assertFalse(r.portao_aberto)
        self.assertIn("Dinheiro: 1 pergunta(s) aberta(s) no núcleo do backend", r.bloqueios)

    def test_hipotese_no_nucleo_fecha_o_portao(self):
        d = self.d()
        d["secoes"]["modelo_dominio"]["afirmacoes"][0] = {"texto": "Talvez exista um Fornecedor.", "hipotese": True}
        self.assertEqual(dossie.conferir(d).bloqueios, ["Modelo de domínio: 1 hipótese(s) no núcleo do backend"])

    def test_hipotese_fora_do_nucleo_nao_fecha(self):
        self.assertTrue(dossie.conferir(self.d()).portao_aberto)  # ameaças e operação têm hipótese no exemplo

    def test_hash_ignora_ordem_das_chaves_e_muda_com_o_conteudo(self):
        d = self.d()
        invertido = json.loads(json.dumps(d), object_pairs_hook=lambda pares: dict(reversed(pares)))
        self.assertEqual(dossie.hash_canonico(d), dossie.hash_canonico(invertido))
        d["versao"] = 2
        self.assertNotEqual(dossie.hash_canonico(d), dossie.hash_canonico(EXEMPLO))

    def test_renderizar_tem_as_14_secoes_e_o_hash(self):
        d = self.d()
        md = dossie.renderizar(d, dossie.conferir(d))
        self.assertIn(dossie.hash_canonico(d), md)
        for n in range(1, 15):
            self.assertIn(f"\n## {n}. ", md)
        self.assertIn("| Integrações | Qual provedor de Pix", md)


class TestCliDossie(unittest.TestCase):
    def rodar(self, *args):
        with redirect_stdout(StringIO()) as saida, redirect_stderr(StringIO()):
            codigo = main(["dossie", *args])
        return codigo, saida.getvalue()

    def test_exemplo(self):
        caminho = str(RAIZ / "descoberta" / "exemplo.json")
        self.assertEqual(self.rodar("conferir", caminho, "--portao")[0], 0)
        codigo, saida = self.rodar("hash", caminho)
        self.assertEqual((codigo, saida.strip()), (0, dossie.hash_canonico(EXEMPLO)))

    def test_portao_fechado_so_falha_com_flag(self):
        d = copy.deepcopy(EXEMPLO)
        d["secoes"]["dinheiro"] = {"estado": "pergunta_aberta",
                                   "perguntas": [{"pergunta": "x", "dono": "y", "prazo": "2026-12-01"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(d, f)
        self.addCleanup(Path(f.name).unlink)
        self.assertEqual(self.rodar("conferir", f.name)[0], 0)
        self.assertEqual(self.rodar("conferir", f.name, "--portao")[0], 1)

    def test_arquivo_invalido(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("{nao e json")
        self.addCleanup(Path(f.name).unlink)
        self.assertEqual(self.rodar("conferir", f.name)[0], 2)
        self.assertEqual(self.rodar("hash", f.name)[0], 2)


if __name__ == "__main__":
    unittest.main()
