import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from fabrica import classe
from fabrica.__main__ import main
from fabrica.classe import Mudanca
from fabrica.projeto import Projeto

PROJ = Projeto(nome="exemplo", modo="desenvolvimento", camada="web-marketing",
               classe_a=("src/publicacao/**", "termos-proibidos.txt"), classe_c=("exemplos/**",))
VAZIO = Projeto(nome="exemplo", modo="manutencao", camada="web-marketing")

TOML = ('nome = "exemplo"\nmodo = "desenvolvimento"\ncamada = "web-marketing"\n'
        '[classes]\na = ["src/publicacao/**"]\n')


def m(*arquivos: str) -> list[Mudanca]:
    return [Mudanca("M", a) for a in arquivos]


class TestClasse(unittest.TestCase):
    def c(self, mudancas, projeto=PROJ):
        return classe.classificar(mudancas, projeto).classe

    def test_portoes_sao_a_mesmo_sem_config_do_projeto(self):
        for f in (".github/workflows/ci.yml", ".github/CODEOWNERS", "CODEOWNERS", ".fabrica/versao",
                  ".fabrica/projeto.toml", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "scripts/testar",
                  "scripts/verificar", ".claude/settings.json", ".codex/config.toml"):
            self.assertEqual(self.c(m(f), VAZIO), "A", f)

    def test_instrucao_de_agente_em_subpasta_e_portao(self):
        # Agentes leem AGENTS.md e CLAUDE.md de subpastas; sem isso, seriam C por serem .md.
        self.assertEqual(self.c(m("src/AGENTS.md")), "A")
        self.assertEqual(self.c(m("docs/sub/CLAUDE.md")), "A")

    def test_portao_casa_sem_diferenciar_caixa(self):
        self.assertEqual(self.c(m("agents.md")), "A")
        self.assertEqual(self.c(m(".GitHub/workflows/ci.yml")), "A")
        self.assertEqual(self.c(m("Scripts/Testar")), "A")

    def test_gatilho_de_adr_e_a(self):
        for f in ("package.json", "site/Dockerfile", "site/dockerfile", "package-lock.json", "pnpm-lock.yaml",
                  "yarn.lock", "uv.lock", "poetry.lock", ".nvmrc", ".python-version", ".npmrc",
                  "requirements-dev.txt", "compose.yaml"):
            self.assertEqual(self.c(m(f)), "A", f)

    def test_caminho_a_do_projeto_sem_diferenciar_caixa(self):
        self.assertEqual(self.c(m("src/publicacao/linkedin.py")), "A")
        self.assertEqual(self.c(m("src/Publicacao/linkedin.py")), "A")
        self.assertEqual(self.c(m("termos-proibidos.txt")), "A")

    def test_documentacao_sozinha_e_c(self):
        self.assertEqual(self.c(m("docs/fluxos-criticos.md", "README.md", "exemplos/post.txt")), "C")

    def test_padrao_c_diferencia_caixa(self):
        # Na dúvida, para cima: o C não ganha casamento por caixa.
        self.assertEqual(self.c(m("Exemplos/post.txt")), "B")

    def test_codigo_comum_e_b(self):
        self.assertEqual(self.c(m("src/rascunho.py")), "B")

    def test_editar_teste_e_b(self):
        self.assertEqual(self.c(m("tests/test_rascunho.py")), "B")
        self.assertEqual(self.c(m("site/src/botao.test.ts")), "B")

    def test_remover_teste_e_a(self):
        for f in ("tests/test_rascunho.py", "site/src/botao.test.ts", "site/e2e/compra.spec.js",
                  "pkg/conftest.py", "t/fluxo.t"):
            r = classe.classificar([Mudanca("D", f)], PROJ)
            self.assertEqual(r.classe, "A", f)
            self.assertIn((f, "A", "remove arquivo de teste"), r.motivos)

    def test_remover_codigo_comum_continua_b(self):
        self.assertEqual(self.c([Mudanca("D", "src/rascunho.py")]), "B")

    def test_mover_teste_e_a(self):
        r = classe.classificar([Mudanca("R", "antigos/rascunho.py", origem="tests/test_rascunho.py")], PROJ)
        self.assertEqual(r.classe, "A")
        self.assertIn(("tests/test_rascunho.py", "A", "move arquivo de teste"), r.motivos)

    def test_rename_conta_a_origem(self):
        # Mover um arquivo de um caminho A para docs/ não rebaixa a classe.
        r = classe.classificar([Mudanca("R", "docs/linkedin.md", origem="src/publicacao/linkedin.md")], PROJ)
        self.assertEqual(r.classe, "A")
        self.assertIn(("docs/linkedin.md", "C", "documentação ou caminho C do projeto"), r.motivos)

    def test_vale_a_mais_severa_do_conjunto(self):
        self.assertEqual(self.c(m("docs/a.md", "src/rascunho.py", ".github/x.yml")), "A")

    def test_diff_vazio_e_c(self):
        self.assertEqual(self.c([]), "C")

    def test_triagem_so_sobe(self):
        self.assertEqual(classe.efetiva("A", "C"), "A")
        self.assertEqual(classe.efetiva("C", "A"), "A")
        self.assertEqual(classe.efetiva(None, "B"), "B")
        self.assertTrue(classe.subiu("C", "A"))
        self.assertFalse(classe.subiu("A", "C"))
        self.assertFalse(classe.subiu(None, "A"))


class TestLerNameStatus(unittest.TestCase):
    def test_um_e_dois_caminhos(self):
        saida = "M\0src/a.py\0D\0tests/test_a.py\0R087\0velho.py\0novo.py\0A\0docs/x.md\0"
        self.assertEqual(classe.ler_name_status(saida), [
            Mudanca("M", "src/a.py"),
            Mudanca("D", "tests/test_a.py"),
            Mudanca("R", "novo.py", origem="velho.py"),
            Mudanca("A", "docs/x.md"),
        ])

    def test_saida_vazia(self):
        self.assertEqual(classe.ler_name_status(""), [])

    def test_status_desconhecido_falha_fechado(self):
        for saida in ("U\0src/a.py\0", "X\0src/a.py\0", "R100\0so-a-origem.py\0", "M\0"):
            with self.assertRaises(classe.ErroClasse, msg=repr(saida)):
                classe.ler_name_status(saida)


def _git(raiz: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@exemplo.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@exemplo.invalid"}
    subprocess.run(["git", "-C", str(raiz), *args], check=True, capture_output=True, env=env)


@unittest.skipUnless(shutil.which("git"), "git não está instalado")
class TestDiffReal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        _git(self.raiz, "init", "-q", "-b", "main")
        (self.raiz / ".fabrica").mkdir()
        (self.raiz / ".fabrica" / "projeto.toml").write_text(TOML, encoding="utf-8")
        (self.raiz / "src").mkdir()
        (self.raiz / "src" / "app.py").write_text("print('oi')\n" * 20, encoding="utf-8")
        (self.raiz / "tests").mkdir()
        (self.raiz / "tests" / "test_app.py").write_text("def test_app():\n    assert True\n" * 10,
                                                         encoding="utf-8")
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "base")
        _git(self.raiz, "checkout", "-q", "-b", "trabalho")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rename_e_remocao_aparecem_com_os_dois_caminhos(self):
        _git(self.raiz, "mv", "src/app.py", "src/principal.py")
        _git(self.raiz, "rm", "-q", "tests/test_app.py")
        _git(self.raiz, "commit", "-q", "-m", "trabalho")
        mudancas = classe.mudancas_do_diff(self.raiz, "main")
        self.assertIn(Mudanca("R", "src/principal.py", origem="src/app.py"), mudancas)
        self.assertIn(Mudanca("D", "tests/test_app.py"), mudancas)
        self.assertEqual(classe.classificar(mudancas, VAZIO).classe, "A")

    def test_cli_com_base(self):
        (self.raiz / "src" / "app.py").write_text("print('tchau')\n", encoding="utf-8")
        _git(self.raiz, "commit", "-q", "-am", "trabalho")
        with redirect_stdout(StringIO()) as saida:
            self.assertEqual(main(["classe", str(self.raiz), "--base", "main", "--declarada", "B"]), 0)
        self.assertIn("classe calculada: B", saida.getvalue())

    def test_ref_inexistente_e_erro(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["classe", str(self.raiz), "--base", "nao-existe"]), 2)

    def test_ref_que_parece_opcao_e_recusada(self):
        with self.assertRaises(classe.ErroClasse):
            classe.mudancas_do_diff(self.raiz, "--output=/tmp/x")


class TestCliClasse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        (raiz / ".fabrica").mkdir()
        (raiz / ".fabrica" / "projeto.toml").write_text(TOML, encoding="utf-8")
        self.raiz = str(raiz)

    def tearDown(self):
        self.tmp.cleanup()

    def rodar(self, *args: str) -> int:
        with redirect_stdout(StringIO()):
            return main(["classe", self.raiz, *args])

    def test_declarado_c_que_toca_caminho_a_falha(self):
        self.assertEqual(self.rodar("--arquivos", "src/publicacao/x.py", "--declarada", "C"), 1)

    def test_declarado_a_com_diff_b_passa(self):
        self.assertEqual(self.rodar("--arquivos", "src/x.py", "--declarada", "A"), 0)

    def test_barra_invertida_do_windows_casa_portao(self):
        self.assertEqual(self.rodar("--arquivos", ".github\\workflows\\ci.yml", "--declarada", "B"), 1)


if __name__ == "__main__":
    unittest.main()
