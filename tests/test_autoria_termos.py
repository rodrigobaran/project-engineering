import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from fabrica import autoria, git, termos
from fabrica.__main__ import main
from fabrica.autoria import Commit

PESSOA = "123+pessoa@users.noreply.github.com"


def commit(autor=PESSOA, committer=PESSOA, mensagem="feat: algo\n"):
    return Commit("a" * 40, "Pessoa", autor, "Pessoa", committer, mensagem)


class TestRevisoes(unittest.TestCase):
    def test_intervalo_normal(self):
        self.assertEqual(git.revisoes("abc..def"), ["abc..def"])

    def test_base_nula_do_push_que_cria_branch(self):
        self.assertEqual(git.revisoes("0" * 40 + "..def"), ["def"])

    def test_intervalo_malformado(self):
        for ruim in ("abc", "..def", "abc..", "--all..x", "a...b"):
            with self.assertRaises(git.ErroGit, msg=ruim):
                git.revisoes(ruim)


class TestAutoria(unittest.TestCase):
    def v(self, *commits):
        return autoria.conferir(list(commits), [PESSOA])

    def test_pessoa_da_lista_passa(self):
        self.assertEqual(self.v(commit()), [])

    def test_email_compara_sem_caixa(self):
        self.assertEqual(self.v(commit(autor=PESSOA.upper())), [])

    def test_agente_como_autor_falha(self):
        self.assertEqual(len(self.v(commit(autor="noreply@anthropic.com"))), 1)

    def test_github_vale_como_committer_do_merge_web_mas_nao_como_autor(self):
        self.assertEqual(self.v(commit(committer="noreply@github.com")), [])
        self.assertEqual(len(self.v(commit(autor="noreply@github.com"))), 1)

    def test_coautor_agente_falha(self):
        msg = "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
        [v] = self.v(commit(mensagem=msg))
        self.assertIn("Co-Authored-By", v.motivo)

    def test_coautor_humano_da_lista_passa(self):
        self.assertEqual(self.v(commit(mensagem=f"feat: x\n\nCo-authored-by: Pessoa <{PESSOA}>\n")), [])

    def test_qualquer_trailer_by_sem_email_da_lista_falha(self):
        self.assertEqual(len(self.v(commit(mensagem="feat: x\n\nSigned-off-by: Bot <bot@exemplo.invalid>\n"))), 1)
        self.assertEqual(len(self.v(commit(mensagem="feat: x\n\nReviewed-by: alguém sem e-mail\n"))), 1)

    def test_marca_de_sessao_falha(self):
        msg = "feat: x\n\nClaude-Session: https://exemplo.invalid/sessao\n"
        self.assertEqual(len(self.v(commit(mensagem=msg))), 1)

    def test_lista_vazia_e_erro(self):
        with self.assertRaises(ValueError):
            autoria.conferir([commit()], [" "])


class TestTermos(unittest.TestCase):
    def test_ignora_caixa_e_acento(self):
        lista = termos.carregar("Padaria São João\n")
        self.assertEqual(len(termos.procurar("x", "a PADARIA SAO JOAO da esquina", lista)), 1)
        self.assertEqual(len(termos.procurar("x", "padaria são joão", lista)), 1)

    def test_linha_e_numero_do_termo(self):
        lista = termos.carregar("# comentário\nalfa\n\nbeta\n")
        self.assertEqual(termos.procurar("f", "nada\ncom beta aqui\n", lista), [termos.Achado("f", 2, 2)])

    def test_sem_lista_falha_fechado(self):
        for vazio in (None, "", "  \n", "# só comentário\n"):
            with self.assertRaises(termos.ErroTermos, msg=repr(vazio)):
                termos.carregar(vazio)

    def test_termo_curto_demais_e_erro(self):
        with self.assertRaises(termos.ErroTermos):
            termos.carregar("ab\n")


def _git(raiz: Path, *args: str, email: str = PESSOA) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "Pessoa", "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": "Pessoa", "GIT_COMMITTER_EMAIL": email}
    subprocess.run(["git", "-C", str(raiz), *args], check=True, capture_output=True, env=env)


@unittest.skipUnless(shutil.which("git"), "git não está instalado")
class TestRepositorioReal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        _git(self.raiz, "init", "-q", "-b", "main")
        (self.raiz / "README.md").write_text("projeto de exemplo\n", encoding="utf-8")
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "base")
        self.base = subprocess.run(["git", "-C", str(self.raiz), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def rodar(self, *args: str, env: dict | None = None) -> tuple[int, str]:
        with mock.patch.dict(os.environ, env or {}), redirect_stdout(StringIO()) as saida, \
                redirect_stderr(StringIO()):
            codigo = main(list(args))
        return codigo, saida.getvalue()

    def test_autoria_pega_commit_de_agente(self):
        (self.raiz / "a.txt").write_text("a\n", encoding="utf-8")
        _git(self.raiz, "add", "a.txt")
        _git(self.raiz, "commit", "-q", "-m", "feat: a\n\nCo-Authored-By: Agente <agente@exemplo.invalid>")
        codigo, saida = self.rodar("autoria", str(self.raiz), "--intervalo", f"{self.base}..HEAD",
                                   "--pessoa", PESSOA)
        self.assertEqual(codigo, 1)
        self.assertIn("Co-Authored-By", saida)

    def test_autoria_limpa_passa(self):
        (self.raiz / "a.txt").write_text("a\n", encoding="utf-8")
        _git(self.raiz, "add", "a.txt")
        _git(self.raiz, "commit", "-q", "-m", "feat: a")
        codigo, saida = self.rodar("autoria", str(self.raiz), "--intervalo", f"{self.base}..HEAD",
                                   "--pessoa", PESSOA)
        self.assertEqual((codigo, "N11: OK em 1 commit(s)\n"), (codigo, saida))

    def test_termos_nao_imprime_o_termo(self):
        (self.raiz / "docs").mkdir()
        (self.raiz / "docs" / "cliente.md").write_text("linha 1\nprojeto Sigiloso Ltda\n", encoding="utf-8")
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "docs: cliente")
        codigo, saida = self.rodar("termos", str(self.raiz), "--intervalo", f"{self.base}..HEAD",
                                   "--texto-env", "PR_CORPO",
                                   env={"TERMOS_PROIBIDOS": "sigiloso ltda\n", "PR_CORPO": "fala da SIGILOSO LTDA"})
        self.assertEqual(codigo, 1)
        self.assertIn("[termo 1] docs/cliente.md:2", saida)
        self.assertIn("[termo 1] $PR_CORPO:1", saida)
        self.assertNotIn("sigiloso", saida.casefold())

    def test_termo_no_nome_do_arquivo_e_na_mensagem(self):
        (self.raiz / "sigiloso-ltda.txt").write_text("nada\n", encoding="utf-8")
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "chore: arquivo da Sigiloso Ltda")
        codigo, saida = self.rodar("termos", str(self.raiz), "--intervalo", f"{self.base}..HEAD",
                                   env={"TERMOS_PROIBIDOS": "sigiloso ltda\n"})
        self.assertEqual(codigo, 1)
        self.assertNotIn("nome do arquivo", saida)  # hífen não casa com espaço: o termo é literal
        codigo, saida = self.rodar("termos", str(self.raiz), "--intervalo", f"{self.base}..HEAD",
                                   env={"TERMOS_PROIBIDOS": "sigiloso\n"})
        self.assertIn("nome do arquivo sigiloso-ltda.txt", saida)
        self.assertIn("mensagem do commit", saida)

    def test_termo_no_titulo_ou_corpo_do_pr_pelo_evento(self):
        evento = self.raiz.parent / f"{self.raiz.name}-evento.json"
        evento.write_text('{"pull_request": {"title": "feat: x", "body": "cita a Sigiloso Ltda"}}', encoding="utf-8")
        self.addCleanup(evento.unlink)
        codigo, saida = self.rodar("termos", str(self.raiz), "--evento", str(evento),
                                   env={"TERMOS_PROIBIDOS": "sigiloso\n"})
        self.assertEqual(codigo, 1)
        self.assertIn("[termo 1] body do PR:1", saida)
        evento.write_text('{"after": "abc"}', encoding="utf-8")  # push: sem PR, nada a conferir
        codigo, _ = self.rodar("termos", str(self.raiz), "--evento", str(evento),
                               env={"TERMOS_PROIBIDOS": "sigiloso\n"})
        self.assertEqual(codigo, 0)

    def test_termos_sem_secret_falha_fechado(self):
        codigo, _ = self.rodar("termos", str(self.raiz), env={"TERMOS_PROIBIDOS": ""})
        self.assertEqual(codigo, 2)

    def test_termos_limpo_passa(self):
        codigo, saida = self.rodar("termos", str(self.raiz), env={"TERMOS_PROIBIDOS": "inexistente\n"})
        self.assertEqual(codigo, 0, saida)


if __name__ == "__main__":
    unittest.main()
