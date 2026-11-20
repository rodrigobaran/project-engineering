<!-- mirror of padrao/NUCLEO.md sha256:0e1dfa98d361c4a97f89196e59c024cb14829e6c4b56c9e4af68883c916187b5; edit the Portuguese source first -->
# Mandatory core (N1 to N11)

Every mandatory rule has verifiable evidence: what is objective,
CI blocks; what requires judgment goes to an independent review recorded in the PR.

| # | Rule | Evidence |
|---|---|---|
| N1 | Everything reaches the main branch through a PR with green checks. No direct push, no force-push, squash merge. | Ruleset with required checks and squash only; gate paths through class A computed from the diff. CODEOWNERS only once agents open PRs under their own identity: a PR's author cannot approve their own PR. |
| N2 | CI runs `verificar` and `testar` on a clean checkout, installing from the lockfile. | Profile workflow. |
| N3 | No secret or sensitive data under version control. | gitleaks on the PR's commits. |
| N4 | A behavior change comes with proof of behavior. | Bug: a test that failed and now passes. New: an acceptance scenario through the real entry point. |
| N5 | The PR states the expected result and the evidence obtained. | Template; CI checks the sections. |
| N6 | A structural decision becomes an ADR. | `ADR:` field in the template; CI fails if the PR touches dependencies, runtime or deploy with the field empty. |
| N7 | PR title in Conventional Commits. | Title check. |
| N8 | Dependencies locked and audited. | Mandatory lockfile; audit on the PR and on a schedule. |
| N9 | `AGENTS.md` is the single source; each tool gets a thin pointer. | Conformance checks the pointers. |
| N10 | An agent's PR is reviewed by another agent or model: reviewer, SHA, findings, conclusion. | Check run from the reviewer App; until then, a comment in a fixed format (`papeis/schemas/revisao.json`). |
| N11 | Human authorship: no agent appears as author, committer or co-author of a commit. Who wrote what goes in the PR description. | CI check: fails if any commit in the PR has `Co-authored-by` or an author/committer outside the project's list of people. |
