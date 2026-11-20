<!-- mirror of padrao/MODOS.md sha256:01f094ca8188ae27d317ea99dada1eb004e88e1b875c5f44130f7c2f7a2faae4; edit the Portuguese source first -->
# Modes

The mode changes the scope of each change, not the rigor. Declared in `.fabrica/projeto.toml`.

**Development:** a project's first PR has no feature: it has `docs/fluxos-criticos.md`,
stack ADRs, `verificar`/`testar` and CI. After that, one critical flow per PR, with an acceptance scenario
through the real entry point. Exploratory code outside the critical flows needs an explicit exception in the PR.

**Maintenance:** N4 applies to every behavior change. The first commit is the test that fails for the
reason of the bug; the second, the fix. A fix is not mixed with refactoring.

**Exit gate** (development → maintenance), all in the same PR: a clean checkout installs and runs
`verificar` and `testar`; every critical flow has a test through the real entry point; the README lets
anyone install, run, test and deploy; a deliberate regression in a critical flow is blocked by CI.
