<!-- mirror of padrao/METODO.md sha256:0c2a4aa2a2a9c76787c73209620a88ff99ac0153c128f89d53e10371eea66e58; edit the Portuguese source first -->
# The agent's working method

1. **Before editing:** find the entry point, the current implementation and the tests. Write in one
   sentence the observable result and the behavior that must be preserved.
2. **While working:** reuse what already solves the problem. Every changed file contributes to acceptance.
   Side refactoring goes to another PR.
3. **Before delivering:** reread the diff as a reviewer. Look for dead code, unused parameters, needless
   abstraction, error handling that hides a failure and tests that pass with the behavior broken.
   Run `verificar` and `testar` and record the real result in the PR.
4. **Independent review:** the reviewer receives the task, the acceptance criterion, the diff and the CI log.
   Each finding points to a file, an input that breaks it and the consequence. A finding without a concrete
   scenario does not block.

Forbidden to the agent: editing `.fabrica/` (it is changed in the factory), removing an assertion or a test
without saying why in the PR, publishing or sending anything outside the repository.
