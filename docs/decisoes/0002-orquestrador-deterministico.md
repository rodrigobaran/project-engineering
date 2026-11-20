# 0002. Orquestrador determinístico, com estado no GitHub e chamadas diretas às APIs

Data: 2026-11-20 · Estado: aceita (PR #10)

## Contexto
A fábrica já tem os papéis (`papeis/`), as classes calculadas pelo diff (`fabrica classe`), os checks de
autoria e de termos e o validador de schema. Falta o motor que leva uma tarefa de ponta a ponta: triagem,
plano, portão humano, implementação, CI, revisão independente e merge. É o primeiro componente que gasta
dinheiro e o primeiro que age sozinho, por isso ele vem por último e começa por este ADR.

## Decisão
1. **Fluxo em código, estado no GitHub.** Um script Python (`fabrica/orquestrar.py`) roda em GitHub Actions
   e trata os repositórios dos projetos como alvos. Cada etapa lê um artefato e grava outro onde a pessoa já
   olha: rótulo da issue, `plano.md` no PR, check run. Nenhum LLM decide a próxima etapa. O modelo produz
   conteúdo; o script lê a CI e o check do revisor e escolhe a rota. Se o orquestrador cair, ele retoma
   pelo estado do PR.
2. **Chamadas diretas às APIs com a biblioteca padrão** (`urllib`, só HTTPS), sem SDK de fornecedor, pela
   regra do ADR 0001. O implementador é um agente de código em modo headless (Claude Code ou Codex)
   instalado no runner: ferramenta da execução, não dependência da fábrica.
3. **Roteamento em `roteamento.toml`:** para cada papel, um titular e dois substitutos de outros
   fornecedores ou de outra cota. Erro 429, 5xx, sobrecarga ou recusa leva a uma nova tentativa respeitando o
   `retry-after`; na segunda falha, o papel passa ao substituto, e a troca vai para o log. Acima de 70% do
   contexto do titular, a chamada vai direto para um modelo com contexto maior.
4. **Saída validada.** Toda saída estruturada passa por `fabrica/esquema.py` contra `papeis/schemas/`.
   Saída inválida ganha uma nova tentativa e, depois, vai para o substituto. Nunca é "consertada" pelo script.
5. **Laços com limite.** Três falhas de CI ou duas reprovações do revisor param a tarefa com o rótulo
   `precisa-humano` e um resumo. O limite leva a tarefa à pessoa, nunca de volta ao início.
6. **Custo com teto duro.** Cada chamada vira uma linha JSONL: papel, fornecedor, modelo, tokens de
   entrada, saída e cache, custo, duração, tarefa, SHA e resultado. Os tetos `ORQ_TETO_TAREFA_USD` e
   `ORQ_TETO_DIA_USD` cortam antes da chamada que os ultrapassaria. Os preços ficam em `roteamento.toml`.
7. **Identidade e N11.** Os commits do implementador saem com o autor e o committer da pessoa responsável
   pelo projeto, e a descrição do PR registra fornecedor, modelo e custo de cada papel. O PR é aberto por um
   GitHub App próprio, e não pela conta da pessoa. Assim o autor do PR deixa de ser quem aprova, e a revisão
   obrigatória (CODEOWNERS) volta a ser possível.
8. **Chave longe de dado não confiável.** O orquestrador guarda as chaves das APIs. O agente de código
   recebe só a credencial da própria execução e nunca as chaves dos outros papéis. Issue, comentário e
   diff entram nos prompts como dado delimitado, nunca como instrução.

## Alternativas consideradas
| Opção | Por que não agora |
|---|---|
| CrewAI Flows | Fluxo por decorators e persistência prontos, mas os agentes não editam código com segurança: ferramentas de arquivo, shell e sandbox teriam de ser escritas à mão. Fica para o bake-off. |
| LangGraph | Grafo de estados com checkpointers e interrupção humana. É mais dependência e mais conceito para manter do que o fluxo pede hoje. Fica para o bake-off. |
| Claude Agent SDK como orquestrador | O modelo dirige o laço, e a decisão aqui é o contrário. Ele só roda modelos Claude, e a revisão precisa de outro fornecedor. Continua candidato a executor do implementador. |
| Agente de nuvem pronto (Codex, Copilot) como motor inteiro | Fornecedor único decide rota, revisão e merge, o que contraria a N10 e a classe calculada por regra. |
| Rodar na extensão do VS Code | O fluxo para quando o notebook fecha. A extensão é painel, não motor. |
| SDK oficial de cada fornecedor | Quatro dependências de execução contra o ADR 0001. As APIs são HTTP simples, e os testes usam respostas gravadas. |

**Bake-off previsto:** depois de 10 tarefas reais com o script, as mesmas 10 tarefas rodam em CrewAI Flows e em
LangGraph, com o executor de código inalterado. Ganha quem tiver menos falhas de orquestração por tarefa e menor
custo. Se ninguém superar o script por margem clara, fica o script: é menos dependência para manter.

## Decisões do responsável (20/11/2026)
1. **Tetos de gasto:** `ORQ_TETO_TAREFA_USD=5` e `ORQ_TETO_DIA_USD=20`, mais um limite mensal de US$ 100 no
   console de cada fornecedor. Quem corta de verdade é o teto do orquestrador, porque em alguns consoles o limite
   só avisa. Um teste prova que a chamada que estouraria o teto não é feita.
2. **Primeiro alvo:** o sistema de marketing do responsável, em modo desenvolvimento. Antes da primeira tarefa,
   o dossiê de descoberta desse sistema precisa estar com o portão aberto. Sem ele, o planejador inventaria
   requisito, que é a hipótese que o portão barra.
3. **GitHub App:** um App próprio abre os PRs, com permissão mínima e instalado só nos repositórios-alvo. Com o
   autor do PR diferente do responsável, o ruleset do alvo passa a exigir a aprovação dele.
4. **Onde o implementador roda:** no runner do GitHub Actions. Em repositório privado, cada execução consome
   minutos do plano, e o JSONL registra a duração para medir esse custo.
5. **Modelos por papel:** a tabela abaixo vai para `roteamento.toml`. Trocar um modelo é um PR nesse arquivo.

| Papel | Titular | 1º substituto | 2º substituto |
|---|---|---|---|
| Triagem | Haiku 5.5 | Gemini 3.8 Flash | grok-4.3 |
| Planejador | Fable 5.2 | Opus 5.5 (outro balde de cota) | grok-4.7 |
| Implementador B/C | Sonnet 5.5 no Claude Code | GPT-6.2 Sol no Codex | manual, fora do fluxo (`precisa-humano`) |
| Implementador A | Opus 5.5 no Claude Code | GPT-6.2 Astra no Codex | Fable 5.2 no Claude Code |
| Revisor de PR escrito por Claude | Gemini 4 Argon | grok-4.7 | GPT-6.2 Astra |
| Revisor de PR escrito por outro fornecedor | Opus 5.5 | Fable 5.2 | outro fornecedor que não seja o autor |
| Revisor de segurança | Gemini 4 Argon | Opus 5.5 | grok-4.7 |

Duas regras valem acima da tabela:
- **O revisor nunca é do fornecedor do autor.** A N10 pede só outro modelo; o plano pede outro fornecedor, e
  vale o mais rígido. Um substituto que caia nessa regra é pulado. Exemplo: no revisor de segurança, o Opus 5.5
  é pulado quando o implementador foi Claude.
- **Dado pessoal de cliente não passa pelo Fable 5.2.** O Fable exige retenção de 30 dias, sem opção de
  retenção zero. Em projeto de cliente com dado pessoal, ele sai de todas as linhas, e o planejador passa a
  ser o Opus 5.5.

## Consequências
- A fábrica passa a ter um componente com acesso de escrita a outros repositórios. O App e o token ficam com o
  mínimo de permissão, por repositório.
- O custo vira número medido por papel. O papel que não paga o próprio custo pode ser cortado com base no log.
- Tudo que o orquestrador faz fica no histórico do GitHub, com o SHA, e pode ser auditado depois.
