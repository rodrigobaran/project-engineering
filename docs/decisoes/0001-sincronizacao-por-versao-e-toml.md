# 0001. Conteúdo compartilhado sincronizado por versão, configuração em TOML, só biblioteca padrão

Data: 2026-11-20 · Estado: aceita (PR #4)

## Contexto
A ideia inicial era ter pastas como `/docs-pj` e `/agents-pj` copiadas de projeto em projeto. Cópia
solta deriva: na terceira cópia, cada projeto tem um prompt de revisor diferente e uma correção não chega
aos outros. A primeira versão do plano previa `projeto.yml` e `classes.yml`.

## Decisão
1. O conteúdo compartilhado mora só aqui. Cada projeto recebe uma cópia em `.fabrica/`, com o SHA da
   fábrica e o sha256 de cada arquivo em `.fabrica/versao`. A CI do projeto roda `conferir` e falha
   com qualquer edição à mão.
2. A configuração do projeto é `.fabrica/projeto.toml`, e as classes ficam dentro dele, não num
   `classes.yml` separado.
3. As ferramentas usam só a biblioteca padrão do Python 3.11+.

## Alternativas descartadas
- **git submodule:** obriga todo clone e toda ferramenta de agente a lidar com submódulo; agentes erram
  isso com frequência.
- **YAML:** exige PyYAML. TOML é lido por `tomllib` desde o Python 3.11, sem dependência.
- **Ler a fábrica em tempo de CI, sem cópia:** o agente de código não veria as regras no checkout, e as
  ferramentas só leem arquivos do próprio repositório.
- **Pacote Python publicado (`pip install`):** traz de volta a dependência que esta decisão evita e
  esconde as regras dentro de `site-packages`, onde o agente não lê.
- **Repositório modelo (template) do GitHub:** copia uma vez, na criação, e nunca mais atualiza. Serve
  para o primeiro commit de um projeto (`modelos/`), não para manter as regras em dia.

## Consequências
- Um agente pode editar um arquivo de `.fabrica/` e o manifesto juntos para enganar a conferência.
  Defesa: `.fabrica/` é caminho de portão (classe A) e está em CODEOWNERS.
- Atualizar a fábrica num projeto é um PR de sincronização, revisado como qualquer outro.
- Workflows reutilizáveis do GitHub (previstos no Padrão v1.1) continuam possíveis para os passos de CI;
  eles complementam a `.fabrica/`, não a substituem, porque o agente não lê workflow remoto.
