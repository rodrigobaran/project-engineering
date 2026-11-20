<!-- mirror of padrao/CLASSES.md sha256:ce73e49b41008be52331e29675431f9ac8f4f9c50919afc0bdeb0e4adaeb162a; edit the Portuguese source first -->
# Risk classes

The class decides whether Rodrigo is called in. That is why it is computed from the diff, by rule
(`python -m fabrica classe`), and not by an LLM's opinion. Triage may declare a class before
the code exists; the more severe one wins. If the diff requires a class above the declared one, the PR goes back to the gate.

| Class | Trigger (any one is enough) | Rodrigo's ok | Implementer | Reviewer (N10 applies to all) |
|---|---|---|---|---|
| A | Gate path; ADR trigger (dependency, runtime, deploy); the project's A path | Required in `plano.md` | Opus 5.5 | Another vendor, required |
| B | Changes code outside the A paths | No | Sonnet 5.5 | Another model; another vendor if it touches a critical flow |
| C | Every file is documentation or a C path of the project | No | Sonnet 5.5 or Haiku | Short checklist |

Gate paths (fixed, the project cannot remove them): `.github/`, `.fabrica/`, `CODEOWNERS` and
`docs/CODEOWNERS`, `scripts/verificar`, `scripts/testar`, and the instructions agents read:
`AGENTS.md`, `CLAUDE.md` and `GEMINI.md` in any folder, `.claude/`, `.codex/`, `.gemini/` and `.cursor/`.
An `AGENTS.md` in a subfolder changes the agent's behavior as much as the root one; without this rule,
it would be C for being `.md`.

ADR triggers: dependency manifests and lockfiles (`package.json`, `package-lock.json`,
`pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `pyproject.toml`, `requirements*.txt`, `poetry.lock`,
`uv.lock`, `Pipfile`, `cpanfile` and the like), package registry (`.npmrc`), runtime version (`.nvmrc`,
`.node-version`, `.python-version`, `.tool-versions`) and deploy (`Dockerfile`, `docker-compose*`,
`compose.*`, `wrangler.toml`), in any folder. Conservative on purpose: a patch bump also
lands in A until CI can read the version. The full list is in `fabrica/classe.py`, in the factory.

Tests are not C by default: removing or weakening a test is the most common way for an agent to pass CI.
Editing a test file is B, and the reviewer looks for weakening. **Removing or moving** a test file is A.

When in doubt, the computation errs upward:
- A patterns (gate, ADR trigger, the project's A path) match case-insensitively, because
  on Windows and macOS `agents.md` and `AGENTS.md` are the same file. C patterns are case-sensitive.
- A rename counts both the source and the destination: moving a file from an A path to `docs/` stays A.
- A git status the computation does not know is an error, not B.
- A `.md` the product uses at runtime, such as a prompt, is not documentation: declare its folder in
  `classes.a` of `projeto.toml`.
