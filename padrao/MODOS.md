# Modos

O modo muda o escopo de cada mudança, não o rigor. Declarado em `.fabrica/projeto.toml`.

**Desenvolvimento:** o primeiro PR de um projeto não tem funcionalidade: tem `docs/fluxos-criticos.md`,
ADRs de stack, `verificar`/`testar` e CI. Depois, um fluxo crítico por PR, com cenário de aceite pelo
ponto de entrada real. Código exploratório fora dos fluxos críticos entra com exceção explícita no PR.

**Manutenção:** N4 vale para toda mudança de comportamento. Primeiro commit é o teste que falha pelo
motivo do bug; o segundo, a correção. Correção não se mistura com refatoração.

**Portão de saída** (desenvolvimento → manutenção), tudo no mesmo PR: checkout limpo instala e roda
`verificar` e `testar`; cada fluxo crítico tem teste pelo ponto de entrada real; o README permite
instalar, rodar, testar e publicar; uma regressão deliberada num fluxo crítico é bloqueada pela CI.
