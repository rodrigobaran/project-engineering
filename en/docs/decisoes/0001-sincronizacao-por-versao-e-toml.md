<!-- mirror of docs/decisoes/0001-sincronizacao-por-versao-e-toml.md sha256:4f2d1e337b1d3828ac534064dd7282ff5ab39a0743eb4c846d2001119a294e15; edit the Portuguese source first -->
# 0001. Shared content synced by version, configuration in TOML, standard library only

Date: 2026-11-20 · Status: accepted (PR #4)

## Context
The initial idea was to have folders like `/docs-pj` and `/agents-pj` copied from project to project. A loose copy
drifts: by the third copy, each project has a different reviewer prompt and a fix does not reach
the others. The first version of the plan called for `projeto.yml` and `classes.yml`.

## Decision
1. The shared content lives only here. Each project gets a copy in `.fabrica/`, with the factory's
   SHA and the sha256 of each file in `.fabrica/versao`. The project's CI runs `conferir` and fails
   on any manual edit.
2. The project's configuration is `.fabrica/projeto.toml`, and the classes live inside it, not in a
   separate `classes.yml`.
3. The tools use only the Python 3.11+ standard library.

## Rejected alternatives
- **git submodule:** forces every clone and every agent tool to deal with submodules; agents get
  this wrong often.
- **YAML:** requires PyYAML. TOML is read by `tomllib` since Python 3.11, with no dependency.
- **Read the factory at CI time, without a copy:** the coding agent would not see the rules in the checkout, and the
  tools only read files from their own repository.
- **Published Python package (`pip install`):** brings back the dependency this decision avoids and
  hides the rules inside `site-packages`, where the agent does not read.
- **GitHub template repository:** copies once, at creation, and never updates again. It serves
  for a project's first commit (`modelos/`), not for keeping the rules up to date.

## Consequences
- An agent could edit a file in `.fabrica/` and the manifest together to fool the check.
  Defense: `.fabrica/` is a gate path, so the change is class A and goes through the human ok.
- Updating the factory in a project is a sync PR, reviewed like any other.
- GitHub reusable workflows remain possible for the CI steps;
  they complement `.fabrica/`, they do not replace it, because the agent does not read a remote workflow.
