<!-- mirror of README.md sha256:8aa7cf1baa11a6a4d864368571b0f9ba9c9098f970d4c0ba1f4752c92f4c5992; edit the Portuguese source first -->
# project-engineering: the factory

[![ci](https://github.com/rodrigobaran/project-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/rodrigobaran/project-engineering/actions/workflows/ci.yml)

Single source of the engineering standard for Rodrigo's projects and of the tools that carry it into each project.
Quality comes from process: what is objective, CI blocks; what requires judgment, an independent
reviewer records in the PR.

Status: v0, experiment. This README describes only what already exists and what CI checks.

Português: [README.md](../README.md). Portuguese is the source; CI flags an outdated translation.

## How this repository grows

Every commit is proposed first, with its content and the alternatives, and only goes in with Rodrigo's ok, through a PR.
No agent appears as the author of a commit (N11): who wrote what is recorded in the PR description.
Architecture decisions live in `docs/decisoes/`.

| Folder | Content | Goes down to the project? |
|---|---|---|
| `padrao/` | Core N1–N11, method, modes, risk classes | Yes, into `.fabrica/padrao/` |
| `camadas/` | What to plan, review and test per kind of software | Yes, the project's layer becomes `.fabrica/camada.md` |
| `papeis/` | Prompts and schemas for triage, planner, implementer, reviewer | Yes, into `.fabrica/papeis/` |
| `fabrica/` | Sync, drift check, class computation, authorship and forbidden-terms checks | No: it runs from here |
| `descoberta/` | Schema, rules and fictitious example of the discovery dossier | No: real dossiers stay outside this repository |
| `precificacao/` | Probabilistic pricing simulator, with a fictitious estimate and history | No |
| `orquestrador/` | Model routing per role, with prices (the cost and failover core and the Anthropic client live in `fabrica/`) | No |
| `docs/decisoes/` | The factory's ADRs | No |
| `en/` | English mirror of every `.md`, with the hash of the original | No |

## Tools

Python 3.11+ standard library only.

```
python -m fabrica sincronizar <project>     # copies standard, layer and roles into <project>/.fabrica/
python -m fabrica conferir <project>        # fails if .fabrica/ was edited by hand
python -m fabrica classe <project> --base origin/main --declarada B
python -m fabrica autoria . --intervalo origin/main..HEAD --pessoa <e-mail>
python -m fabrica termos . --intervalo origin/main..HEAD   # list in $TERMOS_PROIBIDOS
python -m fabrica espelho conferir .        # fails if any translation in en/ fell behind
python -m fabrica espelho carimbar . <file.md>   # records the hash after updating the translation
python -m fabrica dossie conferir <dossier.json> --portao   # discovery rules and gate
python -m fabrica preco simular <estimate.toml> --orcamento 25000   # P50, P80, P95 and scope
python -m fabrica roteamento [--dado-pessoal] [--autor <vendor>]   # who serves each role and who is left out
python -m fabrica contrato anthropic        # real, minimal API call (needs ANTHROPIC_API_KEY)
```

Local verification: `scripts/verificar` (ruff, installed from `.github/requisitos-ci.txt`, and the check of
the `en/` mirror) and `scripts/testar`.

## CI

| Job | What it blocks |
|---|---|
| testes (3.11 and 3.13) | Lint, outdated translation in `en/` and tests |
| autoria (N11) | A commit with an agent as author, committer or co-author |
| termos proibidos | A client's or private project's name in a file, commit or PR. The list is a secret; the log shows only the term's number |

License: MIT.
