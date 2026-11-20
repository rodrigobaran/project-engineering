# Descoberta: o dossiê, com o backend primeiro

Nenhum plano começa sem descoberta. A saída dela é um dossiê com estrutura fixa, e ele é a entrada única
do planejador.

Por que o backend primeiro: o front se refaz em semanas. Já o modelo de dados, as permissões e o
tratamento de dinheiro e de dado pessoal não se refazem assim. Um erro nessas camadas aparece tarde, com
dados reais e integrações presas a ele, e corrigir passa a exigir migração, não só código novo.

Esta pasta é pública e só tem o modelo: o schema, as regras e um exemplo fictício. Dossiês de clientes
reais e o material bruto (entrevistas, planilhas, conversas) nunca entram neste repositório.

## Arquivos

| Arquivo | O que é |
|---|---|
| `schema.json` | A forma do dossiê (JSON Schema). Serve também como saída estruturada para os modelos. |
| `exemplo.json` | Dossiê fictício de encomendas de uma padaria, com o portão aberto. |
| `../fabrica/dossie.py` | As regras que dependem do conteúdo, o portão, o hash e a renderização. |

## As seções

| # | Seção | Pergunta que responde | Saída verificável |
|---|---|---|---|
| 1 | Objetivo | Por que o sistema existe e como saber se deu certo | 1 a 3 métricas com número |
| 2 | Atores e permissões | Quem pode fazer o quê, em quais dados | Matriz papel × ação × recurso |
| 3 | Modelo de domínio | Entidades, relações e o que nunca pode ser falso | Diagrama e lista de invariantes |
| 4 | Ciclos de vida | Por quais estados cada entidade passa | Máquina de estados por entidade |
| 5 | Fluxos críticos | O que não pode quebrar | Cenários "dado, quando, então" |
| 6 | Dados pessoais | Quais dados, base legal, retenção, direitos do titular | Inventário de dados |
| 7 | Dinheiro | Moeda, arredondamento, repetição segura, conciliação | Regras e casos de teste com valores |
| 8 | Integrações | Com quem o sistema conversa e o que acontece quando o outro lado cai | Lista com contrato, limite e modo de falha |
| 9 | Volume e desempenho | Quantos usuários, quantas operações, que espera é aceitável | Números com faixa |
| 10 | Auditoria | Quem precisa saber o que mudou, quando e por quem | Lista de eventos auditáveis |
| 11 | Ameaças | Como cada fluxo crítico pode ser atacado | Ameaças STRIDE com mitigação e teste |
| 12 | Operação | Backup, recuperação, monitoramento, publicação | Metas de RPO e RTO |
| 13 | Fora de escopo | O que não será feito | Lista explícita |
| 14 | Perguntas abertas | O que ainda falta saber | Lista com dono e prazo |

## Regras que `fabrica dossie conferir` cobra

- **Três estados por seção:** `respondida` (com afirmações), `nao_se_aplica` (com o motivo escrito) ou
  `pergunta_aberta` (com perguntas que têm dono e prazo). Seção em branco não passa.
- **Toda afirmação cita a fonte** (arquivo e trecho, linha ou minuto) ou se marca como hipótese. Nunca as
  duas coisas. Duas fontes que se contradizem viram pergunta aberta, nunca escolha silenciosa do modelo.
- **Fluxo crítico respondido tem cenário** "dado, quando, então". Esses cenários viram os testes de aceite
  que a CI cobra (N4): o que o cliente aprovou e o que a máquina testa são o mesmo texto.
- **A seção 14 não é escrita à mão.** Ela é a soma das perguntas das outras seções, para não existirem
  duas listas que divergem.

## Portão da descoberta

O planejamento só começa **sem pergunta aberta e sem hipótese** nas seções 2, 3, 4, 6 e 7, o núcleo do
backend. Hipótese no núcleo é uma pergunta que ninguém fez. Nas outras seções, pergunta aberta pode
seguir, mas entra no preço como risco.

A seção 13 protege o contrato: o que não está escrito como incluído não foi prometido.

## Versão aprovada e contrato

`fabrica dossie hash` calcula o sha256 do JSON canônico (chaves ordenadas, sem espaços, UTF-8). A versão
aprovada, identificada por esse hash, pode ir como anexo técnico do contrato. Mudança de escopo vira
versão nova do dossiê, e a diferença de preço sai do simulador. "Mas eu achei que estava incluído" vira
uma comparação entre duas versões.

## Comandos

```
python -m fabrica dossie conferir descoberta/exemplo.json            # forma e regras
python -m fabrica dossie conferir descoberta/exemplo.json --portao   # falha também com o portão fechado
python -m fabrica dossie hash descoberta/exemplo.json
python -m fabrica dossie renderizar descoberta/exemplo.json > dossie.md
```

## Ainda não está aqui

O pipeline que preenche o dossiê com vários fornecedores (extração, síntese, ataque STRIDE, cliente
difícil, completude) depende do orquestrador e entra depois dele. As saídas por seção ainda são
afirmações em texto; matriz de permissões e máquina de estados com estrutura própria ficam para quando
um projeto real mostrar a forma que serve.
