# Hint 3

For `daily_fetch_attempts`: compute each tier's scheduled-checks-per-day
independently (URLs in that tier times cycles per day for that tier's
interval), add the three tiers together, then multiply the total by the
expected-attempts-per-check factor -- a single scalar that applies
uniformly across tiers because the retry policy and success rate in
`workload.json` aren't tier-specific. That expected-attempts factor is a
sum of `max_attempts` terms, each a power of `(1 - success_rate)`;
term `i` (zero-indexed) is the probability that the first `i` attempts
all failed, which is exactly the probability that attempt `i+1` gets
made at all.

For `required_concurrency`: multiply peak throughput (attempts/second)
by average latency (in seconds, not milliseconds) to get "how many
requests are in flight on average at peak" -- that's Little's Law
directly. Then divide by `target_utilization` to inflate that into a
provisioning target with headroom. `pod_count` is then just that target
divided by per-pod concurrency, rounded up with `math.ceil`.

For egress and cost: every attempt (successes and failures both) pulls
a response over the wire, so the attempt count you already computed for
`daily_fetch_attempts` is exactly the multiplier for bytes-per-day.
Cost is bytes converted to (decimal) gigabytes, scaled from a day to a
30-day month, times the per-GB rate.
