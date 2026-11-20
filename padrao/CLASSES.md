# Classes de risco

A classe decide se o Rodrigo é chamado. Por isso ela é calculada sobre o diff, por regra
(`python -m fabrica classe`), e não pela opinião de um LLM. A triagem pode declarar uma classe antes
do código existir; vale a mais severa. Se o diff exige classe acima da declarada, o PR volta ao portão.

| Classe | Gatilho (qualquer um basta) | Ok do Rodrigo | Implementador | Revisor (N10 vale para todas) |
|---|---|---|---|---|
| A | Caminho de portão; gatilho de ADR (dependência, runtime, deploy); caminho A do projeto | Obrigatório no `plano.md` | Opus 5.5 | Outro fornecedor, obrigatório |
| B | Muda código fora dos caminhos A | Não | Sonnet 5.5 | Outro modelo; outro fornecedor se tocar fluxo crítico |
| C | Todos os arquivos são documentação ou caminho C do projeto | Não | Sonnet 5.5 ou Haiku | Checklist curto |

Caminhos de portão (fixos, o projeto não remove): `.github/`, `.fabrica/`, `CODEOWNERS` e
`docs/CODEOWNERS`, `scripts/verificar`, `scripts/testar`, e as instruções que os agentes leem:
`AGENTS.md`, `CLAUDE.md` e `GEMINI.md` em qualquer pasta, `.claude/`, `.codex/`, `.gemini/` e `.cursor/`.
Um `AGENTS.md` numa subpasta muda o comportamento do agente tanto quanto o da raiz; sem esta regra,
ele seria C por ser `.md`.

Gatilhos de ADR: manifesto e lockfile de dependência (`package.json`, `package-lock.json`,
`pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `pyproject.toml`, `requirements*.txt`, `poetry.lock`,
`uv.lock`, `Pipfile`, `cpanfile` e afins), registro de pacotes (`.npmrc`), versão de runtime (`.nvmrc`,
`.node-version`, `.python-version`, `.tool-versions`) e deploy (`Dockerfile`, `docker-compose*`,
`compose.*`, `wrangler.toml`), em qualquer pasta. Conservador de propósito: um bump de patch também
cai em A até a CI saber ler a versão. A lista completa está em `fabrica/classe.py`, na fábrica.

Testes não são C por padrão: remover ou enfraquecer teste é a forma mais comum de um agente passar na CI.
Editar um arquivo de teste é B, e o revisor procura enfraquecimento. **Remover ou mover** um arquivo de
teste é A.

Na dúvida, o cálculo erra para cima:
- Padrões de A (portão, gatilho de ADR, caminho A do projeto) casam sem diferenciar maiúsculas, porque
  no Windows e no macOS `agents.md` e `AGENTS.md` são o mesmo arquivo. Padrões de C diferenciam.
- Um rename conta a origem e o destino: mover um arquivo de um caminho A para `docs/` continua A.
- Status do git que o cálculo não conhece é erro, não B.
- Um `.md` que o produto usa em execução, como um prompt, não é documentação: declare a pasta em
  `classes.a` do `projeto.toml`.
