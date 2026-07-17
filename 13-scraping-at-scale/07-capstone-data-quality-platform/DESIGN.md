# Capstone Design Memo -- Data Quality Platform

Fill in each section with your own analysis, grounded in what you actually
built and observed across CP1 and CP2 of this capstone, and across tasks
01-06 of this module (recon/pacing, data-quality contracts, change
detection, markup resilience, the budget router, observability).

## Architecture and data flow

[fill in -- walk through `run_pipeline` end to end: discovery, html fetch,
extraction, the quality gate, the budget-router decision, and the render
fetch, in the order they actually happen for one product id. Where does a
product's journey branch (quarantine vs clean; rendered vs not), and what
determines each branch? What does `changedetect.py` reuse from
`pipeline.py` rather than duplicating, and why did you draw that line where
you did?]

## Defense handling: headers, honeypots, pacing

[fill in -- what exactly does your client send to pass the header gate, and
how does your listing parser tell a real product link from a honeypot/trap
link? Name the pacing mechanism you used and explain concretely why a
bounded-concurrency semaphore alone is not enough on this target. Cite the
`rate_limit_violations`/`banned` numbers CP1 and CP2 actually observed for
your implementation across a full-catalog run.]

## Data-quality contract and quarantine strategy

[fill in -- list the six defect shapes your `quality_check` catches and
exactly which signal distinguishes each one (including how you detected
the truncated-description defect). Why does a record failing more than one
rule still produce exactly one quarantine row in your implementation? What
would happen to a bad record if `quality_check` were skipped entirely --
trace one specific defect type through to a concrete downstream failure.]

## Change detection and fingerprint design

[fill in -- what shape does `fingerprint()` actually hash in your
implementation, and why is that shape immune to the volatile nonce by
construction rather than by a special-case exclusion? Walk through what
CP2's idempotent-recovery check actually proved about your
`build_fingerprint_index`/`changed_between` -- what would a NON-idempotent
implementation have done differently on the second call, concretely?]

## Cost and budget tradeoffs

[fill in -- state the modeled cost your CP1 run actually achieved
(completeness, n_rendered, total cost) and compare it to the all-render and
mixed-strategy reference numbers from `data/ground-truth.json`'s
`cost_model`. Why is `review_count` a sufficient signal to gate the render
step on, and what's the worst case for this heuristic -- a scenario where
reading `review_count` from the cheap HTML fetch would mislead the router?]

## Observability

[fill in -- name the seven metric families your pipeline exposes and what
each one would tell a scraping operator watching a live run. Which of your
CP1 run's own metric values (pages fetched by strategy, quarantine reasons,
completeness gauges, latency count) would you actually alert on in
production, and at what threshold, and why those and not others?]

## Scaling to production / 10x

[fill in -- if `n_products` were 40,000 instead of 4,000, what in your
current implementation would need to change first: the pacer's target
rate, the discovery step, the quality gate, the change-detection index's
persistence, something else? What's the first thing that would actually
break (not just "get slower") at 10x, and what's the smallest change that
would fix it? What would you add that this capstone's checkpoints don't
test at all -- retries/backoff strategy, distributed crawling across
multiple client identities, alerting on the Prometheus metrics, structured
logging, anything else you'd want before this ran unattended against a
real hostile site?]
