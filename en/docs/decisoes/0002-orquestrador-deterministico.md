<!-- mirror of docs/decisoes/0002-orquestrador-deterministico.md sha256:f16341730a59526d26a172bade97b89b54ed18b0db628817bced735141f8ea36; edit the Portuguese source first -->
# 0002. Deterministic orchestrator, with state in GitHub and direct API calls

Date: 2026-11-20 · Status: proposed (draft; no code before approval)

## Context
The factory already has the roles (`papeis/`), the classes computed from the diff (`fabrica classe`), the
authorship and forbidden-terms checks and the schema validator. What is missing is the engine that carries a task
end to end: triage, plan, human gate, implementation, CI, independent review and merge. It is the first component
that spends money and the first that acts on its own, which is why it comes last and starts with this ADR.

## Proposed decision
1. **Flow in code, state in GitHub.** A Python script (`fabrica/orquestrar.py`) runs in GitHub Actions
   and treats the projects' repositories as targets. Each step reads one artifact and writes another where the person already
   looks: an issue label, `plano.md` in the PR, a check run. No LLM decides the next step. The model produces
   content; the script reads CI and the reviewer's check and picks the route. If the orchestrator goes down, it resumes
   from the PR's state.
2. **Direct API calls with the standard library** (`urllib`, HTTPS only), with no vendor SDK, per the
   rule in ADR 0001. The implementer is a coding agent in headless mode (Claude Code or Codex)
   installed on the runner: a tool of the run, not a dependency of the factory.
3. **Routing in `roteamento.toml`:** for each role, a primary model and two substitutes from other
   vendors or another quota. A 429, a 5xx, an overload or a refusal leads to one retry honoring
   `retry-after`; on the second failure, the role moves to the substitute, and the switch goes to the log. Above 70% of
   the primary's context, the call goes straight to a model with a larger context.
4. **Validated output.** Every structured output goes through `fabrica/esquema.py` against `papeis/schemas/`.
   An invalid output gets one retry and then goes to the substitute. It is never "fixed" by the script.
5. **Bounded loops.** Three CI failures or two rejections by the reviewer stop the task with the
   `precisa-humano` label and a summary. The limit takes the task to the person, never back to the start.
6. **Cost with a hard ceiling.** Each call becomes one JSONL line: role, vendor, model, input,
   output and cache tokens, cost, duration, task, SHA and result. The ceilings `ORQ_TETO_TAREFA_USD` and
   `ORQ_TETO_DIA_USD` cut before the call that would exceed them. Prices live in `roteamento.toml`.
7. **Identity and N11.** The implementer's commits carry the author and committer of the person responsible
   for the project, and the PR description records vendor, model and cost per role. The PR is opened by its own
   GitHub App, not by the person's account. That way the PR's author is no longer the approver, and required
   review (CODEOWNERS) becomes possible again.
8. **Keys away from untrusted data.** The orchestrator holds the API keys. The coding agent
   gets only the credential of its own run and never the other roles' keys. Issues, comments and
   diffs enter the prompts as delimited data, never as instructions.

## Alternatives considered
| Option | Why not now |
|---|---|
| CrewAI Flows | Decorator-based flow and persistence out of the box, but its agents do not edit code safely: file, shell and sandbox tools would have to be written by hand. Kept for the bake-off. |
| LangGraph | State graph with checkpointers and human interrupts. More dependency and more concepts to maintain than the flow needs today. Kept for the bake-off. |
| Claude Agent SDK as the orchestrator | The model drives the loop, and the decision here is the opposite. It only runs Claude models, and review needs another vendor. Still a candidate to execute the implementer. |
| A ready-made cloud agent (Codex, Copilot) as the whole engine | A single vendor decides route, review and merge, which contradicts N10 and the rule-computed class. |
| Running inside the VS Code extension | The flow stops when the laptop closes. The extension is a dashboard, not the engine. |
| Each vendor's official SDK | Four runtime dependencies against ADR 0001. The APIs are plain HTTP, and the tests use recorded responses. |

**Planned bake-off:** after 10 real tasks with the script, the same 10 tasks run on CrewAI Flows and on
LangGraph, with the code executor unchanged. Whoever has fewer orchestration failures per task and lower
cost wins. If none beats the script by a clear margin, the script stays: it is less dependency to maintain.

## Decisions that belong to the owner, before any code
1. **Spending ceilings:** amount per task and per day, and the monthly limit set in each vendor's console.
2. **First target:** the marketing system, in development mode, or another project.
3. **GitHub App:** create the author App (recommended) or accept, at first, PRs opened by the owner's own account, with no
   required review.
4. **Where the implementer runs:** on the Actions runner (recommended: it does not depend on the laptop being on) or on the
   owner's machine, by remote control.
5. **Models per role:** confirm the plan's table (primary and substitutes) or change it before the first spend.

## Consequences
- The factory gains a component with write access to other repositories. The App and the token get the
  least permission, per repository.
- Cost becomes a measured number per role. A role that does not pay for itself can be cut based on the log.
- Everything the orchestrator does stays in GitHub's history, with the SHA, and can be audited later.
