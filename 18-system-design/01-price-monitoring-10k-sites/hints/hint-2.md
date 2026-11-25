# Hint 2

Retries: a scheduled check isn't one fetch, it's a sequence of up to
`max_attempts` attempts that stops the moment one succeeds. Think of it
as a per-check "how many attempts do I expect to burn" question, and
notice that the answer is a finite sum over a shrinking probability of
still needing another attempt -- not a plain multiplication by
`max_attempts`, and not an infinite geometric series either (it's
capped).

Little's Law relates three quantities: throughput (rate), latency, and
the number of things in flight at once. You have a throughput number
and a latency number already in the workload; the concurrency you need
to provision is one algebraic step away, plus a division that builds in
headroom rather than sizing for 100% utilization.

For scheduling stampede-avoidance in the design doc: think about what
happens if you enqueue all of a tier's URLs at literally the same
instant every cycle, versus spreading them across the interval. The
mechanism matters more than the word "jitter" on its own.
