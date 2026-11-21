"""Cliente da Anthropic contra respostas de teste, sem rede.

As respostas em `tests/respostas/anthropic/` foram montadas a partir da documentação da API, não gravadas de
chamadas reais: formato do streaming e da contagem em https://platform.claude.com/docs/en/api/messages/create,
erros em https://platform.claude.com/docs/en/api/errors e recusa em
https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback. O workflow manual `contrato`
confere o mesmo caminho contra a API de verdade.
"""
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from decimal import Decimal
from pathlib import Path

from fabrica import anthropic, contrato, roteamento, transporte
from fabrica.anthropic import ClienteAnthropic, ErroFornecedor, schema_para_api
from fabrica.chamada import ErroTransitorio, Pedido, Prompt, Recusa, SaidaTruncada
from fabrica.custo import Uso, custo_real
from fabrica.transporte import ErroRede, Requisicao, RespostaHttp, TransporteUrllib

RESPOSTAS = Path(__file__).parent / "respostas" / "anthropic"
ROTA = roteamento.carregar()
HAIKU = ROTA.modelos["haiku-5-5"]
SCHEMA = {"type": "object", "required": ["classe", "motivo"], "properties": {
    "classe": {"type": "string", "enum": ["A", "B", "C"]},
    "motivo": {"type": "string", "minLength": 3},
}}


class TransporteFalso:
    """Devolve as respostas na ordem e guarda cada requisição."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.requisicoes: list[Requisicao] = []

    def enviar(self, requisicao):
        self.requisicoes.append(requisicao)
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def corpo(self, n=-1):
        return json.loads(self.requisicoes[n].corpo)


def resposta(arquivo: str, status: int = 200, **cabecalhos) -> RespostaHttp:
    linhas = (RESPOSTAS / arquivo).read_text(encoding="utf-8").split("\n")
    return RespostaHttp(status, {k.replace("_", "-"): v for k, v in cabecalhos.items()}, iter(linhas))


def pedido(**kw) -> Pedido:
    base = {"tarefa": "t1", "papel": "triagem", "sha": "abc", "tokens_entrada": 1000, "max_saida": 64,
            "conteudo": Prompt("Você classifica mudanças.", "Classifique este diff.")}
    base.update(kw)
    return Pedido(**base)


def cliente(*respostas) -> tuple[ClienteAnthropic, TransporteFalso]:
    t = TransporteFalso(*respostas)
    return ClienteAnthropic("chave-de-teste", t), t


class TestPedido(unittest.TestCase):
    def test_monta_o_pedido_com_streaming_cabecalhos_e_sem_fallback(self):
        c, t = cliente(resposta("ok_texto.sse"))
        c.chamar(HAIKU, pedido(esforco="low"), 64)
        r = t.requisicoes[0]
        self.assertEqual(r.url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(r.cabecalhos["x-api-key"], "chave-de-teste")
        self.assertEqual(r.cabecalhos["anthropic-version"], anthropic.VERSAO)
        self.assertNotIn("anthropic-beta", r.cabecalhos)
        corpo = t.corpo()
        self.assertEqual(corpo["model"], "claude-haiku-5-5")
        self.assertEqual((corpo["max_tokens"], corpo["stream"]), (64, True))
        self.assertEqual(corpo["system"], "Você classifica mudanças.")
        self.assertEqual(corpo["messages"], [{"role": "user", "content": "Classifique este diff."}])
        self.assertEqual(corpo["output_config"], {"effort": "low"})
        for proibido in ("fallbacks", "thinking", "temperature", "cache_control"):
            self.assertNotIn(proibido, corpo)

    def test_a_chave_nunca_aparece_no_repr(self):
        c, t = cliente(resposta("ok_texto.sse"))
        c.chamar(HAIKU, pedido(), 64)
        self.assertNotIn("chave-de-teste", repr(c) + repr(t.requisicoes[0]))

    def test_sem_chave_nao_ha_cliente(self):
        with self.assertRaises(ErroFornecedor):
            ClienteAnthropic.do_ambiente({})

    def test_conteudo_precisa_ser_prompt(self):
        c, _ = cliente(resposta("ok_texto.sse"))
        with self.assertRaises(TypeError):
            c.chamar(HAIKU, pedido(conteudo="texto solto"), 64)

    def test_atende_so_a_anthropic(self):
        c, _ = cliente()
        self.assertTrue(c.atende(HAIKU))
        self.assertFalse(c.atende(ROTA.modelos["gemini-4-argon"]))

    def test_schema_vai_fechado_e_sem_as_palavras_que_a_api_recusa(self):
        enviado = schema_para_api({"type": "object", "properties": {
            "itens": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {
                "nome": {"type": "string", "minLength": 1, "pattern": "^[a-z]+$"}}}}},
            "$defs": {"x": {"type": "object", "properties": {}}}})
        self.assertEqual(enviado, {"type": "object", "additionalProperties": False, "properties": {
            "itens": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
                "nome": {"type": "string"}}}}},
            "$defs": {"x": {"type": "object", "properties": {}, "additionalProperties": False}}})
        self.assertIn("minLength", SCHEMA["properties"]["motivo"])  # o original não muda


class TestStreaming(unittest.TestCase):
    def test_texto_junta_os_blocos_e_ignora_o_pensamento(self):
        c, _ = cliente(resposta("ok_texto.sse"))
        r = c.chamar(HAIKU, pedido(), 64)
        self.assertEqual(r.saida, "Olá, mundo.")
        self.assertEqual(r.uso, Uso(entrada=25, saida=15, cache_leitura=0))

    def test_json_com_schema_vira_objeto_e_o_cache_entra_no_uso(self):
        c, t = cliente(resposta("ok_json.sse"))
        r = c.chamar(HAIKU, pedido(schema=SCHEMA), 256)
        self.assertEqual(r.saida, {"classe": "B", "motivo": "só testes"})
        self.assertEqual(r.uso, Uso(entrada=1200, saida=40, cache_leitura=800))
        formato = t.corpo()["output_config"]["format"]
        self.assertEqual(formato["type"], "json_schema")
        self.assertNotIn("minLength", formato["schema"]["properties"]["motivo"])

    def test_json_ilegivel_volta_como_texto_para_a_validacao_reprovar(self):
        c, _ = cliente(resposta("ok_texto.sse"))
        self.assertEqual(c.chamar(HAIKU, pedido(schema=SCHEMA), 64).saida, "Olá, mundo.")

    def test_recusa_traz_a_categoria_e_o_uso(self):
        c, _ = cliente(resposta("recusa.sse"))
        with self.assertRaises(Recusa) as ctx:
            c.chamar(HAIKU, pedido(), 64)
        self.assertIn("cyber", str(ctx.exception))
        self.assertEqual(ctx.exception.uso, Uso(300, 0, 0))

    def test_saida_truncada_traz_o_uso(self):
        c, _ = cliente(resposta("truncada.sse"))
        with self.assertRaises(SaidaTruncada) as ctx:
            c.chamar(HAIKU, pedido(schema=SCHEMA), 64)
        self.assertEqual(ctx.exception.uso, Uso(500, 64, 0))

    def test_sobrecarga_no_meio_e_transitoria_e_cobra_o_que_ja_saiu(self):
        c, _ = cliente(resposta("sobrecarga_no_meio.sse"))
        with self.assertRaises(ErroTransitorio) as ctx:
            c.chamar(HAIKU, pedido(), 64)
        self.assertEqual(ctx.exception.uso, Uso(900, 1, 0))

    def test_stream_cortado_sem_message_stop_e_transitorio(self):
        c, _ = cliente(resposta("cortado.sse"))
        with self.assertRaisesRegex(ErroTransitorio, "message_stop") as ctx:
            c.chamar(HAIKU, pedido(), 64)
        self.assertEqual(ctx.exception.uso, Uso(700, 1, 0))

    def test_rede_que_cai_no_meio_e_transitoria(self):
        def linhas():
            yield "event: message_start"
            yield ('data: {"type":"message_start","message":{"usage":{"input_tokens":10,"output_tokens":1}}}')
            yield ""
            raise ErroRede("ConnectionResetError")
        c, _ = cliente(RespostaHttp(200, {}, linhas()))
        with self.assertRaises(ErroTransitorio) as ctx:
            c.chamar(HAIKU, pedido(), 64)
        self.assertEqual(ctx.exception.uso, Uso(10, 1, 0))

    def test_rede_que_nem_abre_e_transitoria(self):
        c, _ = cliente(ErroRede("URLError"))
        with self.assertRaises(ErroTransitorio):
            c.chamar(HAIKU, pedido(), 64)

    def test_escrita_de_cache_conta_como_entrada_dobrada(self):
        sse = ('event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":100,'
               '"cache_creation_input_tokens":1000,"output_tokens":1}}}\n\n'
               'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
               '"usage":{"output_tokens":5}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n')
        c, _ = cliente(RespostaHttp(200, {}, iter(sse.split("\n"))))
        self.assertEqual(c.chamar(HAIKU, pedido(), 64).uso, Uso(2100, 5, 0))

    def test_stop_reason_inesperado_e_definitivo(self):
        sse = ('event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}\n\n'
               'event: message_stop\ndata: {"type":"message_stop"}\n\n')
        c, _ = cliente(RespostaHttp(200, {}, iter(sse.split("\n"))))
        with self.assertRaisesRegex(ErroFornecedor, "tool_use"):
            c.chamar(HAIKU, pedido(), 64)


class TestErros(unittest.TestCase):
    def chamar_com(self, arquivo, status, **cabecalhos):
        c, _ = cliente(resposta(arquivo, status, **cabecalhos))
        return lambda: c.chamar(HAIKU, pedido(), 64)

    def test_429_e_transitorio_com_retry_after(self):
        with self.assertRaises(ErroTransitorio) as ctx:
            self.chamar_com("erro_429.json", 429, retry_after="7")()
        self.assertEqual(ctx.exception.retry_after, 7.0)
        self.assertIn("rate_limit_error", str(ctx.exception))

    def test_429_do_limite_de_gasto_para_tudo(self):
        with self.assertRaisesRegex(ErroFornecedor, "limite de gasto"):
            self.chamar_com("erro_429_gasto.json", 429)()

    def test_529_e_5xx_sao_transitorios(self):
        for status in (500, 502, 503, 529):
            with self.subTest(status), self.assertRaises(ErroTransitorio) as ctx:
                self.chamar_com("erro_529.json", status)()
            self.assertIsNone(ctx.exception.retry_after)

    def test_x_should_retry_false_vence_o_status(self):
        with self.assertRaises(ErroFornecedor):
            self.chamar_com("erro_529.json", 529, x_should_retry="false")()

    def test_4xx_e_definitivo(self):
        for arquivo, status in (("erro_401.json", 401), ("erro_400.json", 400)):
            with self.subTest(status), self.assertRaises(ErroFornecedor) as ctx:
                self.chamar_com(arquivo, status)()
            self.assertEqual(ctx.exception.status, status)

    def test_corpo_de_erro_ilegivel_ainda_classifica_pelo_status(self):
        c, _ = cliente(RespostaHttp(503, {}, iter(["<html>bad gateway</html>"])))
        with self.assertRaises(ErroTransitorio):
            c.chamar(HAIKU, pedido(), 64)


class TestContagem(unittest.TestCase):
    def test_conta_com_o_mesmo_corpo_e_margem_para_cima(self):
        c, t = cliente(resposta("contagem.json"))
        self.assertEqual(c.contar(HAIKU, pedido(schema=SCHEMA)), 1020)
        r = t.requisicoes[0]
        self.assertEqual(r.url, "https://api.anthropic.com/v1/messages/count_tokens")
        corpo = t.corpo()
        self.assertNotIn("stream", corpo)
        self.assertNotIn("max_tokens", corpo)
        self.assertEqual(corpo["output_config"]["format"]["type"], "json_schema")

    def test_erro_na_contagem_segue_a_mesma_regra(self):
        c, _ = cliente(resposta("erro_529.json", 529))
        with self.assertRaises(ErroTransitorio):
            c.contar(HAIKU, pedido())

    def test_contagem_ilegivel_e_definitiva(self):
        c, _ = cliente(RespostaHttp(200, {}, iter(['{"tokens": 3}'])))
        with self.assertRaises(ErroFornecedor):
            c.contar(HAIKU, pedido())


class TestCustoDasRespostas(unittest.TestCase):
    def test_custo_da_resposta_com_cache(self):
        c, _ = cliente(resposta("ok_json.sse"))
        r = c.chamar(HAIKU, pedido(schema=SCHEMA), 256)
        # Haiku: 1.200 de entrada a 0,10 + 800 de cache (sem preço próprio: como entrada) + 40 de saída a 0,50
        self.assertEqual(custo_real(HAIKU, r.uso), Decimal("0.000220"))



class TestTransporte(unittest.TestCase):
    def test_so_https(self):
        with self.assertRaises(ValueError):
            TransporteUrllib().enviar(Requisicao("http://api.anthropic.com/v1/messages", {}, b"{}", 1.0))

    def test_queda_no_meio_da_leitura_vira_erro_de_rede_e_fecha(self):
        class Quebra:
            fechada = False

            def __iter__(self):
                yield b"event: ping\r\n"
                raise ConnectionResetError("reset")

            def close(self):
                self.fechada = True

        fonte = Quebra()
        linhas = transporte._linhas(fonte)
        self.assertEqual(next(linhas), "event: ping")
        with self.assertRaises(ErroRede):
            next(linhas)
        self.assertTrue(fonte.fechada)

class TestContrato(unittest.TestCase):
    """O caminho do workflow `contrato`, com o transporte falso no lugar da rede."""

    def sse_ok(self):
        sse = ('event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":40,'
               '"output_tokens":1}}}\n\nevent: content_block_start\ndata: {"type":"content_block_start",'
               '"index":0,"content_block":{"type":"text","text":""}}\n\nevent: content_block_delta\ndata: '
               '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"{\\"ok\\": true}"}}'
               '\n\nevent: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
               '"usage":{"output_tokens":6}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n')
        return RespostaHttp(200, {}, iter(sse.split("\n")))

    def test_contrato_passa_pela_chamada_inteira(self):
        t = TransporteFalso(resposta("contagem.json"), self.sse_ok())
        saida = StringIO()
        with redirect_stdout(saida):
            self.assertEqual(contrato.anthropic({"ANTHROPIC_API_KEY": "k"}, t), 0)
        self.assertIn("haiku-5-5 tentativa 1: ok", saida.getvalue())
        self.assertIn("contrato anthropic: OK com claude-haiku-5-5", saida.getvalue())
        self.assertEqual([r.url.rsplit("/", 1)[-1] for r in t.requisicoes], ["count_tokens", "messages"])

    def test_contrato_reprova_com_o_motivo(self):
        t = TransporteFalso(resposta("contagem.json"), resposta("erro_401.json", 401))
        erro = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(erro):
            self.assertEqual(contrato.anthropic({"ANTHROPIC_API_KEY": "k"}, t), 1)
        self.assertIn("FALHOU: ErroFornecedor: HTTP 401 authentication_error", erro.getvalue())

    def test_contrato_sem_chave_reprova_sem_chamar(self):
        with redirect_stderr(StringIO()):
            self.assertEqual(contrato.anthropic({}, TransporteFalso()), 1)

if __name__ == "__main__":
    unittest.main()
