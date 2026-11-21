<!-- mirror of orquestrador/README.md sha256:eff0c4583c193dae459c08410922186763c9c8e0c98d3f2450d855fb84ed73c4; edit the Portuguese source first -->
# Orchestrator

The engine that takes a task from triage to merge, decided in ADR 0002
(`docs/decisoes/0002-orquestrador-deterministico.md`). It is being built in small PRs. The core decides
**who serves each role and how much that may cost** and is tested with no network and no spend. The first
vendor client, Anthropic's, already makes real calls.

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
- **`fabrica/chamada.py`:** one role call with input counting, ceiling, retry, substitute and output
  validation against the schema. The client that talks to the vendor comes in as a parameter, and a model
  whose vendor has no client is skipped, with the reason.
- **`fabrica/anthropic.py`:** the client for Anthropic's API, standard library only
  (`fabrica/transporte.py`). It counts the input with `count_tokens`, calls with streaming and asks for
  structured output when the role has a schema. The key comes from `ANTHROPIC_API_KEY`.
- **`fabrica/contrato.py` and the `contrato` workflow:** one real, minimal call to Haiku, triggered by hand,
  that checks whether the test responses still match the API. It costs less than US$ 0.001.

```
python -m fabrica roteamento                      # order per role and who is left out
python -m fabrica roteamento --dado-pessoal --autor openai --tokens 400000
python -m fabrica contrato anthropic              # real call; needs ANTHROPIC_API_KEY
```

## Why not the official SDK

Anthropic's SDK would be a new dependency, and the factory uses only the standard library (a dependency calls
for an ADR). It also retries on its own, which would duplicate the rule in `chamada.py`. The price is keeping
the response format by hand. That is what the test responses in `tests/respostas/anthropic/`, built from the
documentation, and the contract, which checks that format against the real API, are for.

Anthropic's server-side `fallbacks` stays off. On a refusal, it would switch models inside the call itself,
at another price, outside the routing table and the log. The switch is made here, in the open.

## The ceiling uses the maximum cost, not the expected one

Before each attempt, the ceiling adds what the task and the day have already spent to the **most** the call
can cost: the counted input plus the maximum output requested, at the price of the tier that applies to that
input. This way spending never goes over the ceiling. The price is sometimes blocking a call that would
have fit.

The input is counted by each candidate's vendor, before the first attempt on it, because each vendor has its
own tokenizer. Anthropic's count is an estimate, so it gets a 2% upward margin. The same count decides whether
the input fits in 70% of the context.

In practice, `max_saida` is a cost decision. With 128 thousand output tokens, one Fable 5.2 call can cost
US$ 5.12, more than the ceiling for a task (US$ 5). Each role will ask for the output it needs.

When the ceiling is hit, the task stops. The orchestrator does not silently switch to a cheaper model,
because that would trade quality for budget without anyone seeing it.

## How a call ends

| Situation | What happens |
|---|---|
| Valid response | The output comes back, and the real cost goes to the log |
| 408, 429, 5xx, overload or network | Waits for `retry-after` (or `espera_padrao_s`) and tries again; on the second failure, goes to the substitute |
| Response that stops midway | Same rule. The tokens the vendor already counted go into spending |
| `retry-after` above `espera_maxima_s` | Goes straight to the substitute, without waiting |
| Refusal | Same rule as a transient error. If the vendor bills the refusal, the cost counts toward spending |
| Output outside the schema | Tries again and then the substitute. The output is never repaired, and the bad one is paid for too |
| Output truncated at `max_saida` | Stops without switching, and pays: the role's limit is wrong, and another model would hide that |
| Console spend limit (Anthropic's 429) | Stops without switching: it is a ceiling, not a failure |
| Any other error (invalid key, malformed request) | Stops without switching: switching vendors would hide the defect |
| Vendor without a client | The model is skipped, with the reason |
| Nobody can serve | `PrecisaHumano`, with each model's reason |

A network drop can happen after the request reached the vendor. In that case there is no way to know whether
the call was billed, and the vendor's console is the source of truth.

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

- The Google, xAI and OpenAI clients. Until then, their models are skipped: triage has no substitute, and
  the review of a PR written by Claude ends in `PrecisaHumano`.
- Each role's effort and output limit, which come with the flow.
- The executor for agent roles (Claude Code and Codex on the runner) and the budget for each run.
- The GitHub flow: labels, `plano.md`, check runs, the limit of 3 CI failures and the GitHub App.
- Where the log is kept between runs, and the run queue, so that two tasks in parallel do not pass the same
  ceiling together.
