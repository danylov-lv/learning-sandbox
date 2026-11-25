No ready-made formulas here -- README.md already pins those precisely.
This is the order to work in, and what each result should make you go
back and check in `INCIDENT.md`.

**First**, work out how many delivery attempts actually result from one
originally-ingested message, given the failure rate and the retry
policy's real (not nominal) behavior. This number should be bigger than
you'd guess from `failure_onset_fraction` alone -- if it isn't, revisit
whether you're treating "max attempts" and the backoff arithmetic
correctly.

**Second**, compare that amplified attempt rate against what the worker
fleet at its given (peak, post-autoscale) size can actually process per
second. Then do the same comparison using `baseline_worker_count`
instead. Two comparisons, not one -- you want to see whether the
autoscale event closed the gap, left it open, or barely moved it.

**Third**, separately from the queue-side math, work out how many
concurrent DB connections the fleet implies at each of those two worker
counts (baseline and peak), and compare both against `db_pool_size`. You
should get one number that's comfortably under the pool size and one
that isn't -- notice which worker count produces which, and cross-check
that against the timestamp of the autoscale event and the timestamp of
the pool alert in `INCIDENT.md`.

**Fourth**, once you have all of that, look at exactly when the
`delivery-api` symptoms start relative to the numbers from step three
(not step two) -- that alignment, or lack of it, is the check that tells
you which of the two mechanisms (queue backlog vs. connection pool) is
actually driving the customer-facing failure, as opposed to just being a
second bad thing happening at the same time.
