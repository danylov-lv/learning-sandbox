# 03 — Delivery pipeline with client SLAs

## Backstory

The scraped-data platform you've been building sells feeds to paying
clients under contract, not just to internal analysts who shrug off a slow
day. Three tiers exist: gold, silver, and bronze, each paying a different
rate for a different promise — a tighter freshness deadline, a higher
monthly availability target, a different delivery mechanism. All three
tiers share the same crawl fleet and the same delivery pipeline. When
crawl or delivery capacity runs short, somebody's promise gets broken
first, and the contract says exactly how much that costs you.

You've spent two years running producer/consumer spiders over RabbitMQ on
Kubernetes — the mechanics of a queue feeding workers is not new to you.
What's new is that the queue now has a price tag attached to lateness, a
formal definition of "available" that a client's lawyer could hold you to,
and a shared budget that cannot always satisfy every tenant at once. This
task is about designing for that: SLA/SLO formalization, error budgets,
priority under a shared pipeline, and what a missed deadline costs in
dollars, not just in a Slack apology.

## What's given

- `workload.json` — three client tiers with client counts, per-client
  daily record volume, freshness deadlines, monthly availability targets,
  delivery batch sizes, and per-breach penalties; a peak-hour
  concentration factor; a per-record delivery cost; a total pipeline drain
  capacity; an outage scenario; and a table of observed breaches for the
  penalty calculation. You do not choose these numbers — the capacity
  model is graded against them (and against perturbed variants of them).
- `src/estimate.py` — nine function stubs, each with a signature, a
  docstring stating its units and rounding rule, and a body of
  `raise NotImplementedError`. No formula is sketched in the code; the
  formula lives in this README's contract section below.
- `DESIGN.md` — an unfilled template with every required `## ` section and
  a final `## Hostile Review` section with `### Q1`-`### Q8` subsections,
  each restating one of `HOSTILE-REVIEW.md`'s questions.
- `HOSTILE-REVIEW.md` — the same eight questions, for reference, in one
  place.
- `tests/validate.py` — the two-gate validator (see Completion criteria).
- `hints/` — three levels of hints. No hint contains a formula or a
  worked number.

## What's required

1. **Design the pipeline in `DESIGN.md`.** Fill in every section: how
   contracts and freshness/availability SLIs/SLOs/SLAs are defined per
   tier; the end-to-end architecture from scrape to delivered batch; the
   contract and wire schemas; how the shared crawl/delivery budget is
   prioritized across tiers without an emergent, undocumented starvation
   policy; delivery transport, retry, and replay semantics (and what
   "exactly-once" really means here); the capacity model in prose,
   referencing your own `estimate.py` output; how breaches are detected
   and reported, not just discovered a month later; the actual
   bottlenecks and failure modes; and how the design changes at 10x
   scale.
2. **Answer the hostile review.** Under `## Hostile Review`, each
   `### Q1`-`### Q8` needs a real, specific answer below the restated
   question — not the question copied back, not a placeholder.
3. **Implement the capacity model in `src/estimate.py`.** All nine
   functions, following the contract below exactly — units, rounding, and
   which rate feeds which formula are all pinned so that your arithmetic
   and the validator's independent recomputation agree.

## Capacity model contract

All quantities are computed from the workload dict as loaded from
`workload.json` (or a validator-constructed variant with the same shape).
Every function takes that dict as its first argument; two also take a
`tier` argument, one of `"gold"`, `"silver"`, `"bronze"`.

- **`records_per_day_total(w) -> float`** — sum, over the three tiers, of
  `client_count * records_per_client_per_day`. Units: records/day.

- **`average_delivery_rps(w) -> float`** — `records_per_day_total(w)`
  spread evenly across a full day: divide by `86400` (seconds/day). Units:
  records/second. This is the average rate — not the peak.

- **`peak_delivery_rps(w) -> float`** — `average_delivery_rps(w) *
  peak_hour_concentration_factor`. Units: records/second.

- **`error_budget_minutes_per_month(w, tier) -> float`** — the allowed
  downtime implied by that tier's `monthly_availability_target_pct`, over
  a **pinned 30-day month** of exactly `30 * 24 * 60 = 43200` minutes.
  Never use a real calendar month (28-31 days) — always `43200`. Formula:
  `(100 - monthly_availability_target_pct) / 100 * 43200`. Units:
  minutes/month. A breach of availability, for this model, is any
  unavailability that eats into this budget — it says nothing about
  freshness on its own (see the distinction the hostile review asks
  about).

- **`deliveries_per_day(w, tier) -> float`** — that tier's total daily
  record volume (`client_count * records_per_client_per_day`) divided by
  its `delivery_batch_size`. Units: batches/day. Do not round — a
  fractional batch count is the expected, correct output (it represents a
  rate, not a literal integer count of batches shipped on any single
  day).

- **`backlog_after_outage(w) -> float`** — records that accumulate while
  the pipeline is fully down for `outage_minutes`. Use the **average**
  delivery rate for this, not peak — an outage is not assumed to coincide
  with the peak hour. Formula: `average_delivery_rps(w) * outage_minutes *
  60`. Units: records.

- **`drain_seconds_after_outage(w) -> float`** — wall-clock time to clear
  that backlog once the pipeline is back up, while the pipeline
  concurrently keeps serving live traffic arriving at the average rate.
  The backlog only drains at the *spare* rate: total drain capacity minus
  the average rate still being consumed by live traffic. Formula:
  `backlog_after_outage(w) / (total_pipeline_drain_capacity_rps -
  average_delivery_rps(w))`. Units: seconds. (The shipped workload and all
  perturbed variants used for grading keep drain capacity above the
  average rate, so this denominator is always positive — if you ever
  compute a non-positive denominator, the workload itself is invalid for
  this model, not your formula.)

- **`freshness_breach_count(w) -> int`** — how many of the three tiers'
  freshness deadlines are blown through by the total time from the start
  of the outage to full recovery. Total recovery time (in minutes) is
  `outage_minutes + drain_seconds_after_outage(w) / 60`. A tier is counted
  as breached if `freshness_deadline_minutes < total_recovery_minutes`
  (strict less-than). Units: a count from 0 to 3.

- **`monthly_penalty_usd(w) -> float`** — total contractual penalty from
  the workload's `observed_breaches` table: for each tier, `observed_breaches[tier]
  * penalty_usd_per_breach`, summed across all three tiers. Units:
  USD/month. This uses the *observed* breach counts in the workload, which
  are independent of (and not derived from) `freshness_breach_count`
  above — that function models one specific outage scenario; this one
  reports what was actually billed last month.

`per_record_delivery_cost_usd` is present in `workload.json` for you to
reason about in `DESIGN.md`'s capacity-model narrative (e.g. total
delivery infra cost per day) — no `estimate.py` function is graded on it
directly.

Every estimate function is checked against the committed `workload.json`
plus at least two perturbed variants the validator builds in memory
(different client counts, different tier mixes, different outage/capacity
numbers). A function that returns a constant tuned to match
`workload.json` alone will fail on the perturbed variants — the check
exists specifically to catch that.

## Completion criteria

From the module root:

```bash
cd 17-system-design
uv run python 03-delivery-with-client-slas/tests/validate.py
```

The validator checks, in order:

1. **Capacity model** — imports `src/estimate.py`, confirms all nine
   functions exist, calls each against the committed workload and two
   in-memory perturbed variants, and compares every result to its own
   independent recomputation of the pinned formula (`rel_tol=1e-6` for
   floats, exact match for `freshness_breach_count`'s integer count).
2. **Design doc** — confirms every required `## ` section in `DESIGN.md`
   exists, meets its minimum length, and has no leftover `[fill in`
   placeholder; confirms at least 8 of the grounding keywords (SLA, SLO,
   error budget, freshness, availability, backpressure, starvation,
   priority, retry, idempotent, replay, backlog, breach, penalty, dead
   letter, webhook) appear somewhere in the document; confirms at least 6
   distinct quantitative tokens (numbers, rates, percentages) appear; and
   confirms all eight `### Q1`-`### Q8` hostile-review subsections are
   genuinely answered (not a verbatim copy of the question, not a
   placeholder, at least 200 characters each).

On success: `PASSED` with a one-line summary. On failure: `NOT PASSED:
<reason>`, exit 1, no traceback.

## Estimated evenings

1

## Topics to read up on

- SLI/SLO/SLA distinctions
- error budgets
- priority scheduling and starvation
- weighted fair queuing
- backpressure
- exactly-once delivery vs idempotent replay
- dead-letter queues and poison-pill handling
- webhook delivery guarantees and retry/backoff design
- contractual penalty structures and how they're reconciled against logs

## `.authoring/` is off-limits

`.authoring/design.md` (at the module root) documents the grading contract
for this module's task-authoring work — not a solution file, but read it
after finishing this task, if at all, same rule as every other module.
