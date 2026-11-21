<!-- mirror of orquestrador/README.md sha256:4e73b91605f12790fd506d17f12075436291294b8e9989560a3e306d25bd63dd; edit the Portuguese source first -->
# Orchestrator

The engine that takes a task from triage to merge, decided in ADR 0002
(`docs/decisoes/0002-orquestrador-deterministico.md`). It is being built in small PRs. This is the first
one: the core that decides **who serves each role and how much that may cost**, tested with no network and
no spend.

## What exists so far

- **`roteamento.toml`:** primary and substitutes for each role, with each model's price, context and maximum
  output. Money is read as `Decimal`, never through `float`.
- **`fabrica/roteamento.py`:** reads the file with strict checking (an unknown field is an error) and removes
  from the queue, with the reason, every candidate that cannot serve:
  - a model with no declared price or context;
  - a reviewer from the same vendor as the PR's author;
  - a model that requires data retention, in a client project with personal data;
  - input above 70% of the model's context.
- **`fabrica/custo.py`:** the JSONL log of every call and the hard ceiling per task and per day
  (`ORQ_TETO_TAREFA_USD` and `ORQ_TETO_DIA_USD`; without them, no call is made).
- **`fabrica/chamada.py`:** one role call with ceiling, retry, substitute and output validation against the
  schema. The client that talks to the vendor comes in as a parameter.

```
python -m fabrica roteamento                      # order per role and who is left out
python -m fabrica roteamento --dado-pessoal --autor openai --tokens 400000
```

## The ceiling uses the maximum cost, not the expected one

Before each attempt, the ceiling adds what the task and the day have already spent to the **most** the call
can cost: the counted input plus the maximum output requested, at the price of the tier that applies to that
input. This way spending never goes over the ceiling. The price is sometimes blocking a call that would
have fit.

In practice, `max_saida` is a cost decision. With 128 thousand output tokens, one Fable 5.2 call can cost
US$ 5.12, more than the ceiling for a task (US$ 5). Each role will ask for the output it needs.

When the ceiling is hit, the task stops. The orchestrator does not silently switch to a cheaper model,
because that would trade quality for budget without anyone seeing it.

## How a call ends

| Situation | What happens |
|---|---|
| Valid response | The output comes back, and the real cost goes to the log |
| 429, 5xx or overload | Waits for `retry-after` (or `espera_padrao_s`) and tries again; on the second failure, goes to the substitute |
| `retry-after` above `espera_maxima_s` | Goes straight to the substitute, without waiting |
| Refusal | Same rule as a transient error. If the vendor bills the refusal, the cost counts toward spending |
| Output outside the schema | Tries again and then the substitute. The output is never repaired, and the bad one is paid for too |
| Any other error (invalid key, malformed request) | Stops without switching: switching vendors would hide the defect |
| Nobody can serve | `PrecisaHumano`, with each model's reason |

Each attempt becomes a line in the log, with role, vendor, model, input, output and cache tokens, cost,
duration, task, SHA and result. A model switch is a line too. An unreadable line in the log is an error:
without the whole log, there is no way to know the spend. The day of the daily ceiling is the UTC day.

## Prices

Prices were checked on 2026-11-20, in US$ per million tokens, and the sources are in `roteamento.toml`. When
the vendor announces a launch price, the later price applies: Gemini 4 Argon's doubles on 2026-12-01, and
Gemini 3.8 Flash's on 2027-01-01. Changing a price is a PR that cites the source, and the price test changes
with it.

Three vendors bill the whole call at a more expensive tier when the input is long: Anthropic on Haiku 5.5,
above 100 thousand tokens; xAI, from 200 thousand; and OpenAI, above 272 thousand. The tier looks at the input
plus cache reads, and inside it the cache is billed as input, the safe side.

## Not here yet

- Each vendor's HTTP client, with recorded responses for the tests.
- Counting tokens before the call. Today it is a parameter, treated as an upper bound.
- The executor for agent roles (Claude Code and Codex on the runner) and the budget for each run.
- The GitHub flow: labels, `plano.md`, check runs, the limit of 3 CI failures and the GitHub App.
- Where the log is kept between runs, and the run queue, so that two tasks in parallel do not pass the same
  ceiling together.
