# Preço probabilístico

Um orçamento de número único esconde o risco. Ou o cliente paga uma margem que ninguém explica, ou o projeto
estoura e a conversa vira briga. Estimativas pontuais erram de forma sistemática para baixo, por otimismo; a
correção conhecida é comparar com projetos parecidos que já terminaram (previsão por classe de referência,
Flyvbjerg). Este simulador é a parte que dá para publicar: a matemática. As taxas, os pesos calibrados e o
histórico de estimado contra real ficam fora deste repositório.

## O modelo

- **Unidade:** cada item de trabalho do dossiê: um fluxo crítico, uma integração, uma entidade com suas
  regras, a infraestrutura.
- **Três pontos por item, em horas:** otimista, provável e pessimista. O planejador propõe e o responsável
  ajusta. A estimativa do modelo é ponto de partida, não verdade.
- **Distribuição PERT** (beta com lambda 4) entre otimista e pessimista, com moda no provável.
- **O risco alarga o pessimista, não o provável.** Cada risco do item (pergunta aberta, integração sem
  documentação, dado pessoal, dinheiro) multiplica a distância entre provável e pessimista por
  `1 + peso`. Os pesos ficam no arquivo de entrada, à vista.
- **Fator de projeto correlacionado.** O mesmo cliente, a mesma ambiguidade e a mesma equipe afetam todos os
  itens ao mesmo tempo. Tratar os itens como independentes faz os erros se cancelarem e a cauda sumir, o erro
  clássico do Monte Carlo ingênuo. Um fator lognormal com mediana 1 é sorteado uma vez por rodada e
  multiplica as horas de todos os itens.
- **Custos fora de hora** (tokens, hospedagem) também têm três pontos. Os que crescem com o trabalho
  (`acompanha_fator = true`) recebem o mesmo fator.
- **Saída:** 10 mil rodadas, só com a biblioteca padrão. Três faixas de horas, custo e prazo: P50 (enxuto),
  P80 (recomendado) e P95 (seguro).

## Onde a incerteza mora

A simulação mostra a fração da variância das horas totais que cada item explica (covariância do item com o
total, dividida pela variância do total; as frações somam 1). É ali que vale gastar mais descoberta, porque
reduzir a incerteza desses itens é o que mais estreita o preço. A incerteza passa a dirigir a descoberta.

## O caminho inverso: o orçamento define o escopo

Com `--orcamento`, o essencial entra inteiro ou a resposta é "o essencial não cabe". Depois, em cada
prioridade (importante, desejável), os itens entram do mais barato ao mais caro enquanto o P80 do conjunto
couber. Todos os conjuntos são comparados nas mesmas rodadas, então a diferença entre eles é de escopo, não de
sorteio. A conversa deixa de ser "está caro" e vira "com esse valor, estes fluxos entram com 80% de chance".

## Calibração: o ponto cego

No começo não há histórico, então os números dos primeiros projetos são palpite organizado e precisam ser
apresentados assim. `calibrar` lê o histórico de estimado contra real e mede, por categoria:

- a **cobertura do P80**: em quantos itens o real ficou até o P80 estimado. Se der 50%, e não 80%, o modelo
  está otimista, e isso aparece em número, não em impressão;
- a **razão mediana real / provável**, que substitui o palpite inicial da categoria a partir de 10 itens.

## Comandos

```
python -m fabrica preco simular precificacao/exemplo.toml
python -m fabrica preco simular precificacao/exemplo.toml --orcamento 25000
python -m fabrica preco calibrar precificacao/historico-exemplo.csv
```

`exemplo.toml` estima o dossiê fictício de `descoberta/exemplo.json`. `historico-exemplo.csv` é inventado e
mostra uma categoria otimista (cobertura de 50%).

## Limites conhecidos

- O fator de projeto é um só. Fatores por categoria (por exemplo, toda integração com o mesmo provedor)
  ficam para quando o histórico mostrar que fazem diferença.
- A escolha de escopo é gulosa, não ótima: maximiza o número de itens em cada prioridade, do mais barato ao
  mais caro. Ela é previsível e fácil de explicar ao cliente, e é por isso que foi escolhida.
- O prazo é horas divididas por horas por semana. Não modela dependência entre itens nem paralelismo.
