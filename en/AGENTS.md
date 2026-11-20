<!-- mirror of AGENTS.md sha256:befa9a76a8d7d48560d0da693ca768f21405ad12adf0037a6ec663589013c5f3; edit the Portuguese source first -->
# Instructions for agents: the factory

This repository is the gate for all the others: every change here is class A and needs Rodrigo's ok.

## Master rule: authorship

- No agent appears as author or co-author of a commit: no `Co-Authored-By`, no session line,
  no agent identity as author or committer. The author is Rodrigo.
- Who wrote what (which agent, which model) is recorded in the PR description, not in the commit.

## How to change

- Propose first: the content of the commit, the message and the alternatives considered. Nothing goes to
  GitHub without Rodrigo's ok for that commit.
- Class A and anything that calls for an ADR: show what you intend to do and the other options before writing code.
- No runtime dependencies: Python 3.11+ standard library only. A new dependency requires an ADR.
- A change in `padrao/`, `camadas/` or `papeis/` changes the behavior of every project at the next
  sync. Say in the PR which projects it affects.
- Decisions go in `docs/decisoes/`.

The rules for the software the factory creates are different and live in `padrao/`.
