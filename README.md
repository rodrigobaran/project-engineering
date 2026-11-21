# project-engineering: a fábrica

[![ci](https://github.com/rodrigobaran/project-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/rodrigobaran/project-engineering/actions/workflows/ci.yml)

Fonte única do padrão de engenharia dos projetos do Rodrigo e das ferramentas que o levam a cada projeto.
A qualidade vem do processo: o que é objetivo, a CI bloqueia; o que exige julgamento, um revisor
independente registra no PR.

Estado: v0, experimento. Este README descreve só o que já existe e o que a CI confere.

English: [en/README.md](en/README.md). O português é a fonte; a CI aponta tradução desatualizada.

## Como este repositório cresce

Cada commit é proposto antes, com o conteúdo e as alternativas, e só entra com o ok do Rodrigo, por PR.
Nenhum agente aparece como autor de commit (N11): quem escreveu o quê fica na descrição do PR.
As decisões de arquitetura ficam em `docs/decisoes/`.

| Pasta | Conteúdo | Desce para o projeto? |
|---|---|---|
| `padrao/` | Núcleo N1–N11, método, modos, classes de risco | Sim, em `.fabrica/padrao/` |
| `camadas/` | O que planejar, revisar e testar por tipo de software | Sim, a camada do projeto vira `.fabrica/camada.md` |
| `papeis/` | Prompts e schemas de triagem, planejador, implementador, revisor | Sim, em `.fabrica/papeis/` |
| `fabrica/` | Sincronização, conferência de deriva, cálculo de classe, checks de autoria e de termos | Não: roda a partir daqui |
| `descoberta/` | Schema, regras e exemplo fictício do dossiê de descoberta | Não: os dossiês reais ficam fora deste repositório |
| `precificacao/` | Simulador de preço probabilístico, com estimativa e histórico fictícios | Não |
| `orquestrador/` | Roteamento de modelos por papel, com preços (o núcleo de custo e de troca está em `fabrica/`) | Não |
| `docs/decisoes/` | ADRs da fábrica | Não |
| `en/` | Espelho em inglês de cada `.md`, com o hash do original | Não |

## Ferramentas

Só biblioteca padrão do Python 3.11+.

```
python -m fabrica sincronizar <projeto>     # copia padrão, camada e papéis para <projeto>/.fabrica/
python -m fabrica conferir <projeto>        # falha se .fabrica/ foi editada à mão
python -m fabrica classe <projeto> --base origin/main --declarada B
python -m fabrica autoria . --intervalo origin/main..HEAD --pessoa <e-mail>
python -m fabrica termos . --intervalo origin/main..HEAD   # lista em $TERMOS_PROIBIDOS
python -m fabrica espelho conferir .        # falha se alguma tradução em en/ ficou para trás
python -m fabrica espelho carimbar . <arquivo.md>   # grava o hash depois de atualizar a tradução
python -m fabrica dossie conferir <dossie.json> --portao   # regras e portão da descoberta
python -m fabrica preco simular <estimativa.toml> --orcamento 25000   # P50, P80, P95 e escopo
python -m fabrica roteamento [--dado-pessoal] [--autor <fornecedor>]   # quem atende cada papel e quem fica de fora
```

Verificação local: `scripts/verificar` (ruff, instalado por `.github/requisitos-ci.txt`, e conferência do
espelho `en/`) e `scripts/testar`.

## CI

| Job | O que bloqueia |
|---|---|
| testes (3.11 e 3.13) | Lint, tradução desatualizada em `en/` e testes |
| autoria (N11) | Commit com agente como autor, committer ou coautor |
| termos proibidos | Nome de cliente ou de projeto privado em arquivo, commit ou PR. A lista é um secret; o log mostra só o número do termo |

Licença: MIT.
