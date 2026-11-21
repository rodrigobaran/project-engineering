# Orquestrador

O motor que leva uma tarefa da triagem ao merge, decidido no ADR 0002
(`docs/decisoes/0002-orquestrador-deterministico.md`). Ele está sendo construído em PRs pequenos. Este é o
primeiro: o núcleo que decide **quem atende cada papel e quanto isso pode custar**, testado sem rede e sem gasto.

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
- **`fabrica/chamada.py`:** uma chamada de papel com teto, nova tentativa, substituto e validação da saída
  pelo schema. O cliente que fala com o fornecedor entra por parâmetro.

```
python -m fabrica roteamento                      # ordem por papel e quem fica de fora
python -m fabrica roteamento --dado-pessoal --autor openai --tokens 400000
```

## O teto usa o custo máximo, não o esperado

Antes de cada tentativa, o teto soma o que a tarefa e o dia já gastaram com o **mais** que a chamada pode
custar: a entrada contada mais a saída máxima pedida, no preço da faixa que vale para aquela entrada. Assim
o gasto nunca passa do teto. O preço disso é barrar, às vezes, uma chamada que caberia.

A consequência prática: `max_saida` é decisão de custo. Com 128 mil tokens de saída, uma chamada do Fable 5.2
pode custar US$ 5,12, mais que o teto de uma tarefa (US$ 5). Cada papel vai pedir a saída de que precisa.

Quando o teto é atingido, a tarefa para. O orquestrador não troca, em silêncio, para um modelo mais barato,
porque isso trocaria qualidade por orçamento sem ninguém ver.

## Como uma chamada termina

| Situação | O que acontece |
|---|---|
| Resposta válida | Volta a saída, e o custo real vai para o log |
| 429, 5xx ou sobrecarga | Espera o `retry-after` (ou `espera_padrao_s`) e tenta de novo; na segunda falha, vai ao substituto |
| `retry-after` acima de `espera_maxima_s` | Vai direto ao substituto, sem esperar |
| Recusa | Mesma regra do erro transitório. Se o fornecedor cobrar a recusa, o custo entra no gasto |
| Saída fora do schema | Tenta de novo e, depois, o substituto. A saída nunca é consertada, e a ruim também é paga |
| Outro erro (chave inválida, pedido malformado) | Para sem trocar: trocar de fornecedor esconderia o defeito |
| Ninguém atende | `PrecisaHumano`, com o motivo de cada modelo |

Cada tentativa vira uma linha no log, com papel, fornecedor, modelo, tokens de entrada, saída e cache,
custo, duração, tarefa, SHA e resultado. A troca de modelo também vira linha. Linha ilegível no log é erro:
sem o log inteiro, não há como saber o gasto. O dia do teto diário é o dia em UTC.

## Preços

Os preços são de 20/11/2026, em US$ por milhão de tokens. Quando a página do fornecedor dava dois valores,
vale o maior. Quatro modelos da tabela do ADR ainda não têm preço conferido (Gemini 3.8 Flash, grok-4.3,
GPT-6.2 Sol e GPT-6.2 Astra) e, por isso, nunca são chamados. Enquanto isso, a triagem fica sem substituto.
Preencher um preço é um PR que cita a fonte.

## Ainda não está aqui

- O cliente HTTP de cada fornecedor, com respostas gravadas para os testes.
- A contagem de tokens antes da chamada. Hoje ela é um parâmetro, tratado como limite superior.
- O executor dos papéis de agente (Claude Code e Codex no runner) e o orçamento de cada execução.
- O fluxo no GitHub: rótulos, `plano.md`, check runs, o limite de 3 falhas de CI e o GitHub App.
- Onde o log fica guardado entre execuções e a fila de execuções, para que duas tarefas em paralelo não
  passem juntas pelo mesmo teto.
