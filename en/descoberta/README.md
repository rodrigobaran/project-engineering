<!-- mirror of descoberta/README.md sha256:9ab913230205f53b38981c6441c89453f9d1542ecd1b4997a43222a320b6266e; edit the Portuguese source first -->
# Discovery: the dossier, backend first

No plan starts without discovery. Its output is a dossier with a fixed structure, and that dossier is the
planner's single input.

Why the backend first: a front end is redone in weeks. The data model, the permissions and the handling
of money and personal data are not. A mistake in those layers shows up late, with real data and
integrations tied to it, and fixing it then requires a migration, not just new code.

This folder is public and holds only the template: the schema, the rules and a fictitious example. Real
clients' dossiers and the raw material (interviews, spreadsheets, conversations) never enter this repository.

## Files

| File | What it is |
|---|---|
| `schema.json` | The dossier's shape (JSON Schema). It also serves as structured output for the models. |
| `exemplo.json` | A fictitious dossier for a bakery's orders, with the gate open. |
| `../fabrica/dossie.py` | The rules that depend on the content, the gate, the hash and the rendering. |

## The sections

| # | Section | Question it answers | Verifiable output |
|---|---|---|---|
| 1 | Objective | Why the system exists and how to know it worked | 1 to 3 metrics with a number |
| 2 | Actors and permissions | Who can do what, on which data | Role × action × resource matrix |
| 3 | Domain model | Entities, relations and what can never be false | Diagram and list of invariants |
| 4 | Lifecycles | Which states each entity goes through | State machine per entity |
| 5 | Critical flows | What must not break | "Given, when, then" scenarios |
| 6 | Personal data | Which data, legal basis, retention, data subject rights | Data inventory |
| 7 | Money | Currency, rounding, safe retries, reconciliation | Rules and test cases with values |
| 8 | Integrations | Whom the system talks to and what happens when the other side goes down | List with contract, limit and failure mode |
| 9 | Volume and performance | How many users, how many operations, what wait is acceptable | Numbers with a range |
| 10 | Audit | Who needs to know what changed, when and by whom | List of auditable events |
| 11 | Threats | How each critical flow can be attacked | STRIDE threats with mitigation and test |
| 12 | Operations | Backup, recovery, monitoring, deploy | RPO and RTO targets |
| 13 | Out of scope | What will not be done | Explicit list |
| 14 | Open questions | What is still unknown | List with owner and deadline |

## Rules that `fabrica dossie conferir` enforces

- **Three states per section:** `respondida` (answered, with statements), `nao_se_aplica` (not applicable,
  with the reason written) or `pergunta_aberta` (open question, with questions that have an owner and a deadline).
  A blank section does not pass.
- **Every statement cites its source** (file and excerpt, line or minute) or is marked as a hypothesis. Never
  both. Two sources that contradict each other become an open question, never a silent choice by the model.
- **An answered critical flow has a scenario** "given, when, then". Those scenarios become the acceptance tests
  CI enforces (N4): what the client approved and what the machine tests are the same text.
- **Section 14 is not written by hand.** It is the sum of the questions in the other sections, so there are
  never two lists that diverge.

## The discovery gate

Planning only starts **with no open question and no hypothesis** in sections 2, 3, 4, 6 and 7, the backend
core. A hypothesis in the core is a question nobody asked. In the other sections an open question may
proceed, but it enters the price as risk.

Section 13 protects the contract: what is not written as included was not promised.

## Approved version and contract

`fabrica dossie hash` computes the sha256 of the canonical JSON (sorted keys, no whitespace, UTF-8). The
approved version, identified by that hash, can go as a technical annex to the contract. A scope change becomes
a new version of the dossier, and the price difference comes from the simulator. "But I thought it was included"
becomes a comparison between two versions.

## Commands

```
python -m fabrica dossie conferir descoberta/exemplo.json            # shape and rules
python -m fabrica dossie conferir descoberta/exemplo.json --portao   # also fails with the gate closed
python -m fabrica dossie hash descoberta/exemplo.json
python -m fabrica dossie renderizar descoberta/exemplo.json > dossie.md
```

## Not here yet

The pipeline that fills the dossier with several vendors (extraction, synthesis, STRIDE attack, difficult
client, completeness) depends on the orchestrator and comes after it. The outputs per section are still
text statements; a permissions matrix and a state machine with their own structure wait until a real
project shows the shape that works.
