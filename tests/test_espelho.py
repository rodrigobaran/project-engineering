import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from fabrica import espelho
from fabrica.__main__ import main


@unittest.skipUnless(shutil.which("git"), "git não está instalado")
class TestEspelho(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        subprocess.run(["git", "-C", str(self.raiz), "init", "-q"], check=True, env=env)
        (self.raiz / "padrao").mkdir()
        self.escrever("README.md", "# Fábrica\n")
        self.escrever("padrao/NUCLEO.md", "# Núcleo\n")

    def tearDown(self):
        self.tmp.cleanup()

    def escrever(self, nome: str, texto: str, binario: bool = False) -> None:
        caminho = self.raiz / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if binario:
            caminho.write_bytes(texto.encode("utf-8"))
        else:
            caminho.write_text(texto, encoding="utf-8")

    def traduzir_tudo(self) -> None:
        self.escrever("en/README.md", "# Factory\n")
        self.escrever("en/padrao/NUCLEO.md", "# Core\n")
        espelho.carimbar(self.raiz, "README.md")
        espelho.carimbar(self.raiz, "padrao/NUCLEO.md")

    def test_sem_traducao(self):
        r = espelho.conferir(self.raiz)
        self.assertEqual(r.faltando, ["README.md", "padrao/NUCLEO.md"])
        self.assertFalse(r.limpo)

    def test_traduzido_e_carimbado_fica_limpo(self):
        self.traduzir_tudo()
        self.assertTrue(espelho.conferir(self.raiz).limpo)
        primeira = (self.raiz / "en/README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(primeira.startswith("<!-- mirror of README.md sha256:"))

    def test_mudar_o_portugues_desatualiza(self):
        self.traduzir_tudo()
        self.escrever("padrao/NUCLEO.md", "# Núcleo\n\nN12 nova.\n")
        self.assertEqual(espelho.conferir(self.raiz).desatualizados, ["en/padrao/NUCLEO.md"])
        espelho.carimbar(self.raiz, "padrao/NUCLEO.md")
        self.assertTrue(espelho.conferir(self.raiz).limpo)

    def test_carimbar_de_novo_nao_duplica_cabecalho(self):
        self.traduzir_tudo()
        espelho.carimbar(self.raiz, "README.md")
        texto = (self.raiz / "en/README.md").read_text(encoding="utf-8")
        self.assertEqual(texto.count("<!-- mirror of"), 1)
        self.assertIn("# Factory", texto)

    def test_crlf_do_windows_tem_o_mesmo_hash(self):
        self.traduzir_tudo()
        self.escrever("README.md", "# Fábrica\r\n", binario=True)
        self.assertTrue(espelho.conferir(self.raiz).limpo)

    def test_cabecalho_ausente_ou_de_outro_arquivo(self):
        self.traduzir_tudo()
        self.escrever("en/README.md", "# Factory sem cabeçalho\n")
        outro = (self.raiz / "en/padrao/NUCLEO.md").read_text(encoding="utf-8").replace(
            "padrao/NUCLEO.md", "README.md", 1)
        self.escrever("en/padrao/NUCLEO.md", outro)
        self.assertEqual(espelho.conferir(self.raiz).sem_cabecalho, ["en/README.md", "en/padrao/NUCLEO.md"])

    def test_traducao_orfa(self):
        self.traduzir_tudo()
        self.escrever("en/antigo.md", "# Old\n")
        self.assertEqual(espelho.conferir(self.raiz).orfaos, ["en/antigo.md"])

    def test_carimbar_sem_traducao_e_erro(self):
        with self.assertRaises(espelho.ErroEspelho):
            espelho.carimbar(self.raiz, "README.md")

    def test_cli(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["espelho", "conferir", str(self.raiz)]), 1)
            self.assertEqual(main(["espelho", "carimbar", str(self.raiz)]), 2)
            self.traduzir_tudo()
            self.assertEqual(main(["espelho", "conferir", str(self.raiz)]), 0)


if __name__ == "__main__":
    unittest.main()
