# Núcleo obrigatório (N1 a N11)

Toda regra obrigatória tem evidência verificável: o que é objetivo
a CI bloqueia; o que exige julgamento vai para revisão independente registrada no PR.

| # | Regra | Evidência |
|---|---|---|
| N1 | Tudo entra na principal por PR com checks verdes. Sem push direto, sem force-push, merge por squash. | Ruleset com checks obrigatórios e só squash; caminhos de portão pela classe A calculada no diff. CODEOWNERS só quando os agentes abrirem PR com identidade própria: o autor de um PR não aprova o próprio PR. |
| N2 | A CI roda `verificar` e `testar` em checkout limpo, instalando pelo lockfile. | Workflow do perfil. |
| N3 | Nenhum segredo ou dado sensível versionado. | gitleaks nos commits do PR. |
| N4 | Mudança de comportamento vem com prova de comportamento. | Bug: teste que falhava e passa. Novo: cenário de aceite pelo ponto de entrada real. |
| N5 | O PR declara resultado esperado e evidência obtida. | Template; a CI confere as seções. |
| N6 | Decisão estrutural vira ADR. | Campo `ADR:` no template; a CI falha se o PR mexe em dependência, runtime ou deploy com o campo vazio. |
| N7 | Título do PR em Conventional Commits. | Check do título. |
| N8 | Dependências travadas e auditadas. | Lockfile obrigatório; auditoria no PR e agendada. |
| N9 | `AGENTS.md` é a fonte única; cada ferramenta recebe um ponteiro fino. | Conformidade confere os ponteiros. |
| N10 | PR de agente é revisado por outro agente ou modelo: revisor, SHA, achados, conclusão. | Check run do App revisor; até lá, comentário em formato fixo (`papeis/schemas/revisao.json`). |
| N11 | Autoria humana: nenhum agente aparece como autor, committer ou coautor de commit. Quem escreveu o quê fica na descrição do PR. | Check na CI: falha se algum commit do PR tem `Co-authored-by` ou autor/committer fora da lista de pessoas do projeto. |
