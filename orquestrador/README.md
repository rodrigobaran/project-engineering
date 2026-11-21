# Orquestrador

O motor que leva uma tarefa da triagem ao merge, decidido no ADR 0002
(`docs/decisoes/0002-orquestrador-deterministico.md`). Ele está sendo construído em PRs pequenos. O núcleo
decide **quem atende cada papel e quanto isso pode custar** e é testado sem rede e sem gasto. O primeiro
cliente de fornecedor, o da Anthropic, já faz chamadas reais.

## O que já existe

- **`roteamento.toml`:** titular e substitutos de cada papel, com preço, contexto e saída máxima de cada
  modelo. O dinheiro é lido como `Decimal`, sem passar por `float`.
- **`fabrica/roteamento.py`:** lê o arquivo com conferência estrita (campo desconhecido é erro) e tira da
  fila, com o motivo, todo candidato que não pode atender:
  - modelo sem preço ou sem contexto declarado;
  - revisor do mesmo fornecedor do autor do PR;
  - modelo que exige retenção de dados, em projeto de cliente com dado pessoal;
  - entrada acima de 70% do contexto do modelo.
- **`fabrica/custo.py`:** o log JSONL de cada chamada e o teto duro por tarefa e por dia
  (`ORQ_TETO_TAREFA_USD` e `ORQ_TETO_DIA_USD`; sem eles, nenhuma chamada é feita).
- **`fabrica/chamada.py`:** uma chamada de papel com contagem da entrada, teto, nova tentativa, substituto e
  validação da saída pelo schema. O cliente que fala com o fornecedor entra por parâmetro, e modelo de
  fornecedor sem cliente é pulado, com o motivo.
- **`fabrica/anthropic.py`:** o cliente da API da Anthropic, só com a biblioteca padrão
  (`fabrica/transporte.py`). Conta a entrada com `count_tokens`, chama com streaming e pede a saída
  estruturada quando o papel tem schema. A chave vem de `ANTHROPIC_API_KEY`.
- **`fabrica/contrato.py` e o workflow `contrato`:** uma chamada real e mínima ao Haiku, disparada à mão, que
  confere se as respostas de teste ainda batem com a API. Custa menos de US$ 0,001.

```
python -m fabrica roteamento                      # ordem por papel e quem fica de fora
python -m fabrica roteamento --dado-pessoal --autor openai --tokens 400000
python -m fabrica contrato anthropic              # chamada real; precisa de ANTHROPIC_API_KEY
```

## Por que sem o SDK oficial

O SDK da Anthropic seria dependência nova, e a fábrica só usa a biblioteca padrão (uma dependência pede ADR).
Ele também faz nova tentativa sozinho, o que duplicaria a regra de `chamada.py`. O preço é manter o formato
das respostas à mão. Para isso servem as respostas de teste em `tests/respostas/anthropic/`, montadas a partir
da documentação, e o contrato, que confere esse formato contra a API de verdade.

O `fallbacks` do servidor da Anthropic fica desligado. Numa recusa, ele trocaria de modelo dentro da própria
chamada, com outro preço, fora da tabela de roteamento e do log. A troca é feita aqui, à vista.

## O teto usa o custo máximo, não o esperado

Antes de cada tentativa, o teto soma o que a tarefa e o dia já gastaram com o **mais** que a chamada pode
custar: a entrada contada mais a saída máxima pedida, no preço da faixa que vale para aquela entrada. Assim
o gasto nunca passa do teto. O preço disso é barrar, às vezes, uma chamada que caberia.

A entrada é contada pelo fornecedor de cada candidato, antes da primeira tentativa nele, porque cada
fornecedor tem o seu tokenizador. A contagem da Anthropic é uma estimativa, então leva 2% de margem para cima.
A mesma contagem decide se a entrada cabe nos 70% do contexto.

A consequência prática: `max_saida` é decisão de custo. Com 128 mil tokens de saída, uma chamada do Fable 5.2
pode custar US$ 5,12, mais que o teto de uma tarefa (US$ 5). Cada papel vai pedir a saída de que precisa.

Quando o teto é atingido, a tarefa para. O orquestrador não troca, em silêncio, para um modelo mais barato,
porque isso trocaria qualidade por orçamento sem ninguém ver.

## Como uma chamada termina

| Situação | O que acontece |
|---|---|
| Resposta válida | Volta a saída, e o custo real vai para o log |
| 408, 429, 5xx, sobrecarga ou rede | Espera o `retry-after` (ou `espera_padrao_s`) e tenta de novo; na segunda falha, vai ao substituto |
| Resposta que para no meio | Mesma regra. O que o fornecedor já contou de tokens entra no gasto |
| `retry-after` acima de `espera_maxima_s` | Vai direto ao substituto, sem esperar |
| Recusa | Mesma regra do erro transitório. Se o fornecedor cobrar a recusa, o custo entra no gasto |
| Saída fora do schema | Tenta de novo e, depois, o substituto. A saída nunca é consertada, e a ruim também é paga |
| Saída truncada no `max_saida` | Para sem trocar e paga: o limite do papel está errado, e outro modelo esconderia isso |
| Limite de gasto do console (429 da Anthropic) | Para sem trocar: é um teto, não uma falha |
| Outro erro (chave inválida, pedido malformado) | Para sem trocar: trocar de fornecedor esconderia o defeito |
| Fornecedor sem cliente | O modelo é pulado, com o motivo |
| Ninguém atende | `PrecisaHumano`, com o motivo de cada modelo |

Uma queda de rede pode acontecer depois de o pedido chegar ao fornecedor. Nesse caso não dá para saber se a
chamada foi cobrada, e o console do fornecedor é a fonte da verdade.

Cada tentativa vira uma linha no log, com papel, fornecedor, modelo, tokens de entrada, saída e cache,
custo, duração, tarefa, SHA e resultado. A troca de modelo também vira linha. Linha ilegível no log é erro:
sem o log inteiro, não há como saber o gasto. O dia do teto diário é o dia em UTC.

## Preços

Os preços foram conferidos em 20/11/2026, em US$ por milhão de tokens, e as fontes estão no `roteamento.toml`.
Quando o fornecedor anuncia um preço de lançamento, vale o de depois: o do Gemini 4 Argon dobra em 1/12/2026,
e o do Gemini 3.8 Flash, em 1/1/2027. Mudar um preço é um PR que cita a fonte, e o teste dos preços muda junto.

Três fornecedores cobram a chamada inteira numa faixa mais cara quando a entrada é longa: a Anthropic no
Haiku 5.5, acima de 100 mil tokens; o xAI, a partir de 200 mil; e a OpenAI, acima de 272 mil. A faixa olha a
entrada somada à leitura de cache e, dentro dela, o cache é cobrado como entrada, o lado seguro.

## Ainda não está aqui

- Os clientes do Google, do xAI e da OpenAI. Até lá, os modelos deles são pulados: a triagem fica sem
  substituto, e a revisão de PR escrito por Claude termina em `PrecisaHumano`.
- O esforço e o limite de saída de cada papel, que entram junto com o fluxo.
- O executor dos papéis de agente (Claude Code e Codex no runner) e o orçamento de cada execução.
- O fluxo no GitHub: rótulos, `plano.md`, check runs, o limite de 3 falhas de CI e o GitHub App.
- Onde o log fica guardado entre execuções e a fila de execuções, para que duas tarefas em paralelo não
  passem juntas pelo mesmo teto.
