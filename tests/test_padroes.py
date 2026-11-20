import unittest

from fabrica.padroes import casa


class TestPadroes(unittest.TestCase):
    def test_diretorio_com_barra_casa_tudo_dentro(self):
        self.assertTrue(casa(".github/workflows/ci.yml", ".github/"))
        self.assertTrue(casa(".fabrica/papeis/revisor.md", ".fabrica/"))
        self.assertFalse(casa("src/.github.py", ".github/"))

    def test_ponto_inicial_nao_e_removido(self):
        # Regressão: lstrip("./") apagaria o ponto de ".fabrica" e o portão deixaria de casar.
        self.assertTrue(casa("./.fabrica/versao", ".fabrica/"))

    def test_estrela_nao_atravessa_diretorio(self):
        self.assertTrue(casa("docs/a.md", "docs/*.md"))
        self.assertFalse(casa("docs/sub/a.md", "docs/*.md"))

    def test_duas_estrelas_atravessam_e_aceitam_zero_diretorios(self):
        self.assertTrue(casa("package.json", "**/package.json"))
        self.assertTrue(casa("site/package.json", "**/package.json"))
        self.assertTrue(casa("docs/sub/a.md", "**/*.md"))

    def test_caminho_exato(self):
        self.assertTrue(casa("AGENTS.md", "AGENTS.md"))
        self.assertFalse(casa("docs/AGENTS.md", "AGENTS.md"))

    def test_barra_invertida_do_windows(self):
        self.assertTrue(casa("scripts\\verificar", "scripts/verificar"))


if __name__ == "__main__":
    unittest.main()
