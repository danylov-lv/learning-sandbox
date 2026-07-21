# 01 -- Price Monitoring at 10,000-Site Scale

## Backstory

Your team has been asked to design (not build -- yet) a system that
watches roughly two million product URLs spread across about 10,000
retail sites and detects price changes. Not every URL needs the same
freshness: a flash-sale-prone electronics retailer needs to be checked
every few minutes, while a slow-moving furniture catalog is fine being
checked once a day. Leadership wants two numbers before they approve a
budget: how many worker pods this needs, and how much the proxy bill
will be. Before either number means anything, they want the design
written down -- what the components are, how scheduling avoids hammering
every site at once, and what breaks first when it breaks.

This is a whiteboard-review exercise done in files instead of at a
whiteboard. Nobody is going to run this system; the validator checks
that your design document has the right shape and that your capacity
arithmetic is actually a formula, not a number you guessed.

## What's given

- `workload.json` -- the committed scale parameters for this design:
  total tracked URLs, the three freshness tiers, response size, fetch
  latency, parse cost, retry policy, worker sizing, target utilization,
  proxy cost, and the peak-hour traffic factor. Read every field before
  you start -- the capacity model contract below is written against
  these exact names.
- `HOSTILE-REVIEW.md` -- eight questions a hostile staff-engineer
  reviewer will ask about this specific design. You answer these inside
  `DESIGN.md`.
- `DESIGN.md` -- an unfilled template with every required section and
  every hostile-review subsection already in place as `[fill in ...]`
  placeholders.
- `src/estimate.py` -- seven function stubs, each `raise
  NotImplementedError`, each documented with its units and rounding rule.
  The arithmetic itself is not in the scaffold -- it's pinned in this
  README's capacity model contract below.
- `tests/validate.py` -- the validator. Read it if you like; it will not
  show you the formula in a more spoiler-shaped way than this README
  already does.

## What's required

1. **Fill in `DESIGN.md`.** Every `## ` section, then every `### Q1`
   through `### Q8` hostile-review answer. Write the design first --
   components, data flow, scheduling strategy, failure modes, the 10x
   story -- before you touch the capacity model. A good answer to a
   hostile-review question sometimes means going back and changing an
   earlier section once you notice the gap it exposes.
2. **Implement `src/estimate.py`.** Seven pure functions over the
   workload dict, computing the numbers your capacity-model section
   describes in prose. Follow the contract below exactly -- the
   validator recomputes each value independently and will reject an
   answer that's merely "close in spirit."

## Capacity model contract

All seven functions take the workload dict `w` as their only argument.
Nothing is read from disk inside `estimate.py` -- the validator passes
in the committed `workload.json` and also perturbed copies of it, so
every function must be a real function of `w`, not a constant.

Fixed conventions used throughout (state these, don't rederive them):

- A day has exactly `1440` minutes and `86400` seconds.
- A month is exactly `30` days for this exercise (no calendar realism).
- `1 GB = 1,000,000,000 bytes` (decimal GB, matching how proxy providers
  bill egress -- not the binary `2^30` gibibyte).

### `daily_fetch_attempts(w) -> float`

For each tier in `w["tiers"]`, the number of scheduled checks per day
for that tier is:

```
tier_checks_per_day = total_tracked_urls * tier.fraction * (1440 / tier.refresh_interval_minutes)
```

Sum this across all three tiers to get `daily_scheduled_checks`.

Each scheduled check may take more than one fetch attempt: attempts are
retried only on failure, up to `max_attempts` attempts total, and each
attempt independently succeeds with probability `success_rate_first_attempt`
(call it `p`). The expected number of attempts consumed by one scheduled
check, given `max_attempts = n`, is the finite series

```
expected_attempts_per_check = sum_{i=0}^{n-1} (1 - p)^i
```

(attempt `i+1` happens if and only if all `i` attempts before it failed;
there is no attempt after a success, and no attempt past the `n`-th
regardless of outcome).

```
daily_fetch_attempts = daily_scheduled_checks * expected_attempts_per_check
```

Return the float, unrounded -- this is an expected value, not something
that literally happened.

### `average_fetches_per_second(w) -> float`

```
average_fetches_per_second = daily_fetch_attempts(w) / 86400
```

Unrounded.

### `peak_fetches_per_second(w) -> float`

Traffic is not uniform across the day; `w["peak_hour_factor"]` is the
ratio of the busiest hour's rate to the day's average rate.

```
peak_fetches_per_second = average_fetches_per_second(w) * peak_hour_factor
```

Unrounded.

### `required_concurrency(w) -> float`

Apply Little's Law at peak: the number of requests in flight equals
throughput times latency. Latency here is `avg_fetch_latency_ms`
converted to seconds.

```
in_flight_at_peak = peak_fetches_per_second(w) * (avg_fetch_latency_ms / 1000)
required_concurrency = in_flight_at_peak / target_utilization
```

Dividing by `target_utilization` (a fraction in `(0, 1]`) converts the
raw in-flight figure into a provisioning target that leaves headroom --
if you only ever provisioned exactly for the raw in-flight number, the
fleet would be running at 100% utilization at peak, with zero slack.
Unrounded.

### `pod_count(w) -> int`

```
pod_count = ceil(required_concurrency(w) / worker_concurrency_per_pod)
```

Round UP to the nearest whole pod. Return an `int` (or an integer-valued
float -- the validator checks the numeric value, not the Python type).

### `egress_bytes_per_day(w) -> float`

Every fetch attempt -- including retries -- pulls a full response over
the proxy and is billed as egress, whether or not that attempt
ultimately succeeded.

```
egress_bytes_per_day = daily_fetch_attempts(w) * avg_response_size_bytes
```

Unrounded.

### `monthly_proxy_cost_usd(w) -> float`

```
monthly_proxy_cost_usd = egress_bytes_per_day(w) * 30 / 1_000_000_000 * proxy_cost_usd_per_gb
```

Unrounded.

## Completion criteria

From the module root (`17-system-design/`):

```bash
uv run python 01-price-monitoring-10k-sites/tests/validate.py
```

Prints `PASSED` on success, or a single `NOT PASSED: <reason>` line and
a non-zero exit code otherwise -- including on the stock, unfilled task.

## Estimated evenings

1

## Topics to read up on

- Little's law
- Tail latency and utilization
- Crawl scheduling and politeness
- Error budgets
- Thundering herd / stampede avoidance and jitter
- Retry storms and correlated vs. independent failure
- Proxy pool economics (residential vs. datacenter egress pricing)
- Zipf-distributed workloads and per-key fairness
