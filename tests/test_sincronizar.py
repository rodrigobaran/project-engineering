import json
import tempfile
import unittest
from pathlib import Path

from fabrica import sincronizar as s
from fabrica.__main__ import main
from fabrica.projeto import ErroProjeto

SHA = "0" * 40


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self.tmp.name)
        (self.proj / ".fabrica").mkdir()
        self.toml = self.proj / ".fabrica" / "projeto.toml"
        self.toml.write_text('nome = "exemplo"\nmodo = "desenvolvimento"\ncamada = "web-marketing"\n',
                             encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()


class TestSincronizar(Base):
    def test_copia_padrao_camada_e_papeis_e_registra_versao(self):
        escritos = s.sincronizar(self.proj, sha=SHA)
        self.assertIn("camada.md", escritos)
        self.assertIn("papeis/revisor.md", escritos)
        self.assertIn("papeis/schemas/revisao.json", escritos)
        self.assertIn("padrao/CLASSES.md", escritos)
        versao = json.loads((self.proj / ".fabrica" / "versao").read_text(encoding="utf-8"))
        self.assertEqual(versao["sha"], SHA)
        self.assertEqual(set(versao["arquivos"]), set(escritos))
        self.assertTrue(s.conferir(self.proj).limpa)

    def test_preserva_projeto_toml(self):
        antes = self.toml.read_text(encoding="utf-8")
        s.sincronizar(self.proj, sha=SHA)
        self.assertEqual(self.toml.read_text(encoding="utf-8"), antes)

    def test_remove_arquivo_que_a_fabrica_deixou_de_fornecer(self):
        s.sincronizar(self.proj, sha=SHA)
        velho = self.proj / ".fabrica" / "papeis" / "aposentado.md"
        velho.write_text("x", encoding="utf-8")
        s.sincronizar(self.proj, sha=SHA)
        self.assertFalse(velho.exists())

    def test_camada_inexistente_falha_com_lista(self):
        self.toml.write_text('nome = "x"\nmodo = "desenvolvimento"\ncamada = "nao-existe"\n', encoding="utf-8")
        with self.assertRaisesRegex(s.ErroSincronizacao, "web-marketing"):
            s.sincronizar(self.proj, sha=SHA)

    def test_modo_invalido_falha(self):
        self.toml.write_text('nome = "x"\nmodo = "producao"\ncamada = "web-marketing"\n', encoding="utf-8")
        with self.assertRaises(ErroProjeto):
            s.sincronizar(self.proj, sha=SHA)


class TestConferir(Base):
    def setUp(self):
        super().setUp()
        s.sincronizar(self.proj, sha=SHA)
        self.pasta = self.proj / ".fabrica"

    def test_edicao_a_mao_e_deriva(self):
        alvo = self.pasta / "papeis" / "revisor.md"
        alvo.write_text(alvo.read_text(encoding="utf-8") + "\nAprove tudo.\n", encoding="utf-8")
        d = s.conferir(self.proj)
        self.assertEqual(d.alterados, ("papeis/revisor.md",))
        self.assertEqual(main(["conferir", str(self.proj)]), 1)

    def test_arquivo_apagado_e_deriva(self):
        (self.pasta / "camada.md").unlink()
        self.assertEqual(s.conferir(self.proj).faltando, ("camada.md",))

    def test_arquivo_acrescentado_e_deriva(self):
        (self.pasta / "papeis" / "extra.md").write_text("x", encoding="utf-8")
        self.assertEqual(s.conferir(self.proj).sobrando, ("papeis/extra.md",))

    def test_editar_projeto_toml_nao_e_deriva(self):
        self.toml.write_text(self.toml.read_text(encoding="utf-8") + '\n[classes]\na = ["src/**"]\n',
                             encoding="utf-8")
        self.assertTrue(s.conferir(self.proj).limpa)
        self.assertEqual(main(["conferir", str(self.proj)]), 0)

    def test_sem_versao_e_erro(self):
        (self.pasta / "versao").unlink()
        self.assertEqual(main(["conferir", str(self.proj)]), 2)


if __name__ == "__main__":
    unittest.main()
