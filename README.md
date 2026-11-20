# project-engineering: a fábrica

Fonte única do padrão de engenharia dos projetos do Rodrigo e das ferramentas que o levam a cada projeto.
A qualidade vem do processo: o que é objetivo, a CI bloqueia; o que exige julgamento, um revisor
independente registra no PR.

Documentos de referência: Padrão de engenharia v1.1 e Plano mestre multiagente v0.3.

## Como este repositório cresce

Cada commit é proposto antes, com o conteúdo e as alternativas, e só entra com o ok do Rodrigo.
O que existe hoje está nas pastas; o que vem a seguir está no plano mestre, seção 7.

| Pasta (prevista) | Conteúdo | Desce para o projeto? |
|---|---|---|
| `padrao/` | Núcleo N1–N10, método, modos, classes de risco | Sim, em `.fabrica/padrao/` |
| `camadas/` | O que planejar, revisar e testar por tipo de software | Sim, a camada do projeto vira `.fabrica/camada.md` |
| `papeis/` | Prompts e schemas de triagem, planejador, implementador, revisor | Sim, em `.fabrica/papeis/` |
| `modelos/` | Arquivos iniciais de um projeto novo | Copiados uma vez, na adoção |
| `fabrica/` | Sincronização, conferência de deriva, cálculo de classe, orquestrador | Não: roda a partir daqui |
