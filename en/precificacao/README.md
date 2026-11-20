<!-- mirror of precificacao/README.md sha256:c5c165b65e2241d29ea51fbfa337fd43843935f93f2c4c3e9caa84aed0f90ea4; edit the Portuguese source first -->
# Probabilistic pricing

A single-number quote hides the risk. Either the client pays a margin nobody explains, or the project
overruns and the conversation turns into a fight. Point estimates err systematically low, out of optimism; the
known fix is to compare with similar projects that already finished (reference class forecasting,
Flyvbjerg). This simulator is the part that can be published: the math. Rates, calibrated weights and the
history of estimated versus actual stay outside this repository.

## The model

- **Unit:** each work item of the dossier: a critical flow, an integration, an entity with its
  rules, the infrastructure.
- **Three points per item, in hours:** optimistic, most likely and pessimistic. The planner proposes and the
  owner adjusts. The model's estimate is a starting point, not the truth.
- **PERT distribution** (beta with lambda 4) between optimistic and pessimistic, with its mode at the most likely.
- **Risk widens the pessimistic point, not the most likely.** Each risk on the item (open question, integration
  without documentation, personal data, money) multiplies the distance between most likely and pessimistic by
  `1 + weight`. The weights live in the input file, in plain sight.
- **Correlated project factor.** The same client, the same ambiguity and the same team affect every
  item at once. Treating items as independent makes the errors cancel out and the tail disappear, the
  classic mistake of naive Monte Carlo. A lognormal factor with median 1 is drawn once per round and
  multiplies the hours of every item.
- **Non-hour costs** (tokens, hosting) also have three points. Those that grow with the work
  (`acompanha_fator = true`) get the same factor.
- **Output:** 10 thousand rounds, standard library only. Three ranges of hours, cost and schedule: P50 (lean),
  P80 (recommended) and P95 (safe).

## Where the uncertainty lives

The simulation shows the fraction of the variance of total hours that each item explains (the item's covariance
with the total, divided by the variance of the total; the fractions add up to 1). That is where more discovery
pays off, because reducing the uncertainty of those items is what narrows the price the most. Uncertainty starts
to drive discovery.

## The inverse path: the budget defines the scope

With `--orcamento`, the essential items go in whole or the answer is "the essential does not fit". Then, within each
priority (important, nice to have), items go in from cheapest to most expensive while the set's P80
fits. Every set is compared on the same rounds, so the difference between them is scope, not
luck of the draw. The conversation stops being "it's expensive" and becomes "with this amount, these flows go in with an 80% chance".

## Calibration: the blind spot

At first there is no history, so the numbers of the first projects are an organized guess and must be
presented as such. `calibrar` reads the history of estimated versus actual and measures, per category:

- the **P80 coverage**: in how many items the actual stayed at or below the estimated P80. If it is 50%, not 80%, the model
  is optimistic, and that shows up as a number, not an impression;
- the **median actual / most likely ratio**, which replaces the category's initial guess from 10 items on.

## Commands

```
python -m fabrica preco simular precificacao/exemplo.toml
python -m fabrica preco simular precificacao/exemplo.toml --orcamento 25000
python -m fabrica preco calibrar precificacao/historico-exemplo.csv
```

`exemplo.toml` estimates the fictitious dossier in `descoberta/exemplo.json`. `historico-exemplo.csv` is made up and
shows an optimistic category (50% coverage).

## Known limits

- There is a single project factor. Factors per category (for example, every integration with the same provider)
  wait until the history shows they make a difference.
- The scope choice is greedy, not optimal: it maximizes the number of items within each priority, from cheapest to
  most expensive. It is predictable and easy to explain to the client, and that is why it was chosen.
- The schedule is hours divided by hours per week. It does not model dependencies between items or parallel work.
