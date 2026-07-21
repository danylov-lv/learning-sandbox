# 05 — Outage Postmortem & Redesign

## Backstory

You've operated scraping systems for two years — daily producer/consumer
spiders over RabbitMQ, on Kubernetes, backends in Django/FastAPI/NestJS.
You've watched dashboards during a bad night. What you probably haven't
had to do yet is write the postmortem: turn a messy pile of logs, alerts,
and a confused on-call channel into a causal chain that actually holds
together, put numbers on how bad it was, and redesign the system so the
same *class* of failure can't recur — not just patch the one symptom
someone happened to notice first.

This task is inverted relative to the rest of this module. Every other
task in `17-system-design` hands you a greenfield brief and asks you to
design forward. This one hands you a wreck and asks you to reconstruct
backward: what actually happened, in what order, and why did each layer's
"reasonable" response make the next layer worse.

## What's given

- **`INCIDENT.md`** — a timestamped timeline and a set of evidence
  fragments (monitoring readings, an alert, a config snippet, restart
  counts, chat excerpts) from a real-feeling 4-hour outage. **This file
  contains no analysis and no root-cause statement, by design.** Nobody in
  the incident channel had the full picture while it was happening, and
  neither will you on first read. Your job in `DESIGN.md`'s "Causal chain"
  section is to reconstruct the chain the evidence implies — the same way
  you'd do it in a real postmortem, from logs and timestamps, not from
  being told the answer. Read it more than once. Some evidence is
  load-bearing; some is texture. Cross-reference timestamps against each
  other before you commit to a story.
- **`workload.json`** — the numeric parameters behind the incident:
  ingest rate, retry policy, worker fleet size, DB pool size and hold
  time, queue depth readings, the delivery API's traffic and error
  budget. These are consistent with the numbers quoted in `INCIDENT.md` —
  if your model of the incident produces numbers that contradict the
  evidence, that's a signal your causal story is wrong somewhere, not
  that the workload file has a typo.
- **`src/estimate.py`** — function stubs, each raising `NotImplementedError`,
  with a docstring stating units and rounding rule but no arithmetic.
- **`DESIGN.md`** — an unfilled template (structure only).
- **`HOSTILE-REVIEW.md`** — eight numbered questions specific to this
  incident. Answer them inside `DESIGN.md`'s final section (`### Q1`
  through `### Q8`), not in this file.

## What's required

1. **Reconstruct the causal chain** and write it into `DESIGN.md`'s
   "Causal chain" section — the full path from first anomaly to
   customer-facing impact to how it was actually stopped, with the
   mechanism at each hop (not just "X happened, then Y happened," but
   *why* Y followed from X).
2. **Quantify it.** Implement all nine functions in `src/estimate.py`
   against the formulas pinned below. These aren't decorative — the
   numbers they produce (retry amplification, peak backlog, pool
   oversubscription, error-budget burn) are exactly the figures a real
   postmortem's "Impact" section would report, and `DESIGN.md`'s
   "Quantified analysis" section should reference them.
3. **Redesign the weak point(s)** — not just "add a circuit breaker"
   as a slogan, but a specific mechanism at each layer that failed, sized
   against the same capacity model (e.g. what pool size or bulkhead
   configuration would have kept `pool_saturation_ratio` under 1.0 at the
   fleet size the autoscaler actually reached).
4. **Fill in `DESIGN.md`** completely — every section, every hostile-review
   answer under `### Q1`–`### Q8`.

## Quantitative model contract

All nine functions take the workload dict (loaded from `workload.json`,
or a perturbed variant of it) as their first argument. Field names below
are exactly the keys in `workload.json`.

- **`retry_amplification_factor(w)`** — effective attempts delivered per
  originally-ingested message. A message that begins failing (a
  `failure_onset_fraction` share of all messages) is assumed to exhaust
  every one of `retry_max_attempts` total delivery attempts (the
  original attempt plus all requeues) before the incident's window ends
  — it never succeeds on a later retry, since nothing about a retry
  changes what the target is serving. A message that never begins
  failing is delivered successfully on its first attempt (1 attempt).
  `retry_amplification_factor = (1 - failure_onset_fraction) * 1
  + failure_onset_fraction * retry_max_attempts`.
  (`retry_backoff_base_ms` and `retry_backoff_factor` are not separate
  terms in this formula — read `INCIDENT.md`'s retry-policy snippet
  and workload.json's backoff fields together and decide for yourself
  whether they change the rate at which retries actually arrive.)
- **`effective_ingest_rps(w)`** — the rate of delivery attempts (original
  plus retries) the worker fleet must actually process per second:
  `steady_state_ingest_rps * retry_amplification_factor(w)`.
- **`queue_growth_rps(w)`** — offered load minus the fleet's processing
  capacity at the workload's given (peak) fleet size. Fleet capacity is
  `worker_count * concurrency_per_worker / avg_attempt_seconds`
  (total concurrent processing slots divided by the average wall time
  per attempt, giving a maximum sustained throughput). `queue_growth_rps
  = effective_ingest_rps(w) - (worker_count * concurrency_per_worker
  / avg_attempt_seconds)`. May be negative (fleet keeping up).
- **`queue_depth_at_minute(w, minute)`** — a single-phase linear model:
  the backlog grows at a constant rate of `queue_growth_rps(w)`
  starting from `initial_queue_depth` at minute 0. `queue_depth_at_minute
  = initial_queue_depth + queue_growth_rps(w) * 60 * minute`. This is a
  deliberate simplification — it does not model a separate, slower growth
  phase before the fleet reached its peak size. Use the peak-fleet growth
  rate for the whole window; don't try to piece together a two-phase
  model.
- **`peak_queue_depth(w)`** — `queue_depth_at_minute(w,
  onset_to_fix_minutes)`, i.e. the backlog at the moment of manual
  intervention.
- **`connections_demanded(w)`** — concurrent DB connections implied by
  the (peak) worker fleet, assuming the fleet is fully saturated (true
  whenever backlog exists, which it does throughout this incident): of
  the fleet's `worker_count * concurrency_per_worker` total concurrent
  processing slots, the expected fraction occupying a DB connection at
  any instant equals the fraction of one attempt's duration that the DB
  connection is actually held for. `connections_demanded = worker_count
  * concurrency_per_worker * (db_connection_hold_ms / 1000)
  / avg_attempt_seconds`.
- **`pool_saturation_ratio(w)`** — `connections_demanded(w) /
  db_pool_size`. A value above 1.0 means the fleet's expected concurrent
  connection demand exceeds what the pool can hand out.
- **`drain_seconds(w)`** — time to clear the peak backlog once the fault
  is fixed (no more amplification — failing messages stop failing),
  while live steady-state traffic keeps arriving throughout the drain:
  `peak_queue_depth(w) / (drain_capacity_rps - steady_state_ingest_rps)`.
- **`error_budget_burn_fraction(w)`** — share of the delivery API's
  monthly error budget consumed by this incident. Monthly budget, in
  requests: `delivery_api_rps * (days_per_month * 24 * 3600) * (1 -
  delivery_api_availability_target)`. Requests actually failed during
  the incident: `delivery_api_rps * (delivery_api_impact_minutes * 60) *
  delivery_api_error_rate_during_incident`. `error_budget_burn_fraction =
  incident_failed_requests / monthly_budget_requests`. Values above 1.0
  mean this single incident alone exceeded the entire month's allowance.

No function rounds its result — every one returns the exact float per
the formula above. `queue_depth_at_minute` and everything downstream of
it accept fractional minutes.

## Completion criteria

From the module root (`17-system-design/`):

```bash
uv run python 05-outage-postmortem-redesign/tests/validate.py
```

Prints `PASSED` on success, or a single `NOT PASSED: <reason>` line and a
non-zero exit code otherwise.

## Estimated evenings

1

## Topics to read up on

- Retry amplification and exponential backoff with jitter
- Bulkheads and circuit breakers
- Connection pool exhaustion
- Metastable failures
- Blameless postmortems
- Error budgets and error-budget burn rate
- Autoscaling on the wrong signal
- Dead-letter queues and poison-message handling
