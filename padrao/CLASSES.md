# Classes de risco

A classe decide se o Rodrigo é chamado. Por isso ela é calculada sobre o diff, por regra
(`python -m fabrica classe`), e não pela opinião de um LLM. A triagem pode declarar uma classe antes
do código existir; vale a mais severa. Se o diff exige classe acima da declarada, o PR volta ao portão.

| Classe | Gatilho (qualquer um basta) | Ok do Rodrigo | Implementador | Revisor (N10 vale para todas) |
|---|---|---|---|---|
| A | Caminho de portão; gatilho de ADR (dependência, runtime, deploy); caminho A do projeto | Obrigatório no `plano.md` | Opus 5.5 | Outro fornecedor, obrigatório |
| B | Muda código fora dos caminhos A | Não | Sonnet 5.5 | Outro modelo; outro fornecedor se tocar fluxo crítico |
| C | Todos os arquivos são documentação ou caminho C do projeto | Não | Sonnet 5.5 ou Haiku | Checklist curto |

Caminhos de portão (fixos, o projeto não remove): `.github/`, `.fabrica/`, `AGENTS.md`, `CLAUDE.md`,
`CODEOWNERS`, `scripts/verificar`, `scripts/testar`.

Gatilhos de ADR: `package.json`, `pyproject.toml`, `requirements*.txt`, `cpanfile`, `Dockerfile`,
`docker-compose*.yml`, `wrangler.toml`. Conservador de propósito: um bump de patch também cai em A até
a CI saber ler a versão.

Testes não são C por padrão: remover ou enfraquecer teste é a forma mais comum de um agente passar na CI.
