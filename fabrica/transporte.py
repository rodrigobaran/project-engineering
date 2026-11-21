"""Transporte HTTP mínimo para os clientes dos fornecedores, só com a biblioteca padrão.

O cliente monta a `Requisicao` e lê a `RespostaHttp` linha a linha, o que serve para JSON e para streaming
(SSE). O transporte é trocável: nos testes, um transporte falso devolve respostas montadas a partir da
documentação do fornecedor, sem rede.

Uma falha de rede vira `ErroRede`. Ela pode acontecer depois de o pedido chegar ao fornecedor, então não dá
para saber se a chamada foi cobrada: o console do fornecedor é a fonte da verdade nesse caso.
"""
from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol


class ErroRede(Exception):
    """A conexão não abriu, caiu no meio ou passou do tempo limite."""


@dataclass(frozen=True)
class Requisicao:
    url: str
    cabecalhos: Mapping[str, str]
    corpo: bytes
    tempo_limite_s: float  # entre um pedaço e outro da resposta, não para a resposta inteira

    def __repr__(self) -> str:  # nunca mostra cabeçalhos: um deles é a chave
        return f"Requisicao({self.url!r}, {len(self.corpo)} bytes)"


@dataclass
class RespostaHttp:
    status: int
    cabecalhos: Mapping[str, str]  # nomes em minúsculas
    linhas: Iterator[str]  # o corpo, linha a linha, sem o fim de linha

    def corpo(self) -> str:
        return "\n".join(self.linhas)


class Transporte(Protocol):
    def enviar(self, requisicao: Requisicao) -> RespostaHttp: ...


def _linhas(resposta) -> Iterator[str]:
    try:
        for bruta in resposta:
            yield bruta.decode("utf-8").rstrip("\r\n")
    except (OSError, http.client.HTTPException) as e:
        raise ErroRede(f"a resposta parou no meio: {type(e).__name__}: {e}") from e
    finally:
        resposta.close()


class TransporteUrllib:
    """POST com `urllib`. Respeita HTTPS_PROXY e os certificados do sistema, como o resto da biblioteca."""

    def enviar(self, requisicao: Requisicao) -> RespostaHttp:
        if not requisicao.url.startswith("https://"):
            raise ValueError(f"só HTTPS: {requisicao.url!r}")
        pedido = urllib.request.Request(  # noqa: S310 (só https, conferido acima)
            requisicao.url, data=requisicao.corpo, headers=dict(requisicao.cabecalhos), method="POST")
        try:
            resposta = urllib.request.urlopen(pedido, timeout=requisicao.tempo_limite_s)  # noqa: S310
        except urllib.error.HTTPError as e:  # 4xx e 5xx: o corpo traz o motivo
            resposta = e
        except (OSError, http.client.HTTPException) as e:  # URLError é OSError, e o tempo limite também
            raise ErroRede(f"{type(e).__name__}: {e}") from e
        cabecalhos = {k.lower(): v for k, v in resposta.headers.items()}
        return RespostaHttp(resposta.status, cabecalhos, _linhas(resposta))
