# 04 -- Multi-Tenant Platform

## Backstory

The scraping platform you've been running in-house is being opened up to
paying customers. Instead of one team's spiders hitting one team's queue,
you'll now have several tenants -- some paying enterprise money, some on a
starter plan -- sharing the same crawler fleet, the same message queue,
the same proxy pool, and the same object storage. Nobody gets a dedicated
cluster; the economics only work if the infrastructure is shared.

That raises every question your Kubernetes-and-RabbitMQ background has
trained you to answer for *jobs*, but now for *tenants*: what's isolated
and what's shared, and why; how you admit a new tenant without letting
them starve the others; how a finite crawl budget gets split fairly when
total demand exceeds capacity; what stops one tenant's badly-behaved
target site (or badly-written selectors) from degrading service for
everyone else; how you attribute shared infrastructure cost back to each
tenant so pricing isn't a guess; and where the hard security boundary
sits between one tenant's data and the next tenant's.

This task asks you to design that multi-tenancy model and back it with a
small capacity/allocation model: given a fixed platform crawl budget and a
table of tenants with different weights and demand, who gets what, what
does it cost to serve them, and where does the platform run out of room.

## What's given

- `workload.json` -- five tenants (`acme_enterprise`, `borealis_pro`,
  `cirrus_pro`, `delta_starter`, `ember_starter`) each with a plan tier, a
  fair-share weight, a demanded request rate, an average response size, an
  existing storage footprint, a monthly plan price, and a burst-allowance
  multiplier; plus platform-wide numbers: total crawl capacity, a target
  utilization (headroom) factor, an admission-time overcommit ratio, a
  shared proxy egress budget, per-unit infrastructure costs, and the
  seconds-per-month convention to use for all monthly conversions.
- `src/estimate.py` -- eight function stubs, each raising
  `NotImplementedError`, with a docstring stating its contract. No
  arithmetic is given -- the formulas are pinned below, not in the code.
- `DESIGN.md` -- an unfilled template with every required section heading
  already in place, each body a `[fill in: ...]` placeholder.
- `HOSTILE-REVIEW.md` -- eight numbered, specific, uncomfortable questions
  about this design. You answer them inside `DESIGN.md`'s
  `## Hostile Review` section (`### Q1` .. `### Q8`), not in this file.
- `tests/validate.py` -- the validator. Read it if you want (it is not a
  spoiler -- it recomputes each formula independently and tersely, it
  does not explain the reasoning), but the formula spec lives here, in
  this README.

## What's required

1. Fill in `DESIGN.md` end to end, including the hostile-review answers.
   Write the design *before* the code -- the capacity model is only
   arithmetic once the design's shape (what's shared, what's isolated, how
   fair share is defined, how cost is attributed) is settled.
2. Implement all eight functions in `src/estimate.py` against the capacity
   model contract below.

## Capacity model contract

All functions take the loaded `workload.json` dict (`w`) as their only
argument. Dict-returning functions are keyed exactly by the tenant ids
used in `workload.json`. Nothing here is rounded except where explicitly
stated -- return plain floats (or, for the one function that returns a
count, a plain `int`).

Fixed conventions used throughout:

- **1 GB = 1,000,000 KB** (decimal/SI units throughout -- 1 KB = 1000
  bytes, 1 GB = 1000 MB = 1,000,000 KB). Do not use binary (1024-based)
  units anywhere in this task.
- **1 month = `w["seconds_per_month"]` seconds** (2,592,000 in the shipped
  file -- a flat 30-day month). Always read this from the workload dict,
  never hardcode 2,592,000 in your code, since a perturbed workload may
  use a different value.
- "Usable capacity" always means
  `w["platform_capacity_rps"] * w["target_utilization"]` -- the physical
  crawl capacity after the headroom the platform deliberately keeps free.

### `total_demand_rps(w) -> float`

Sum of `demand_rps` across every tenant in `w["tenants"]`.

### `overcommit_ratio(w) -> float`

`total_demand_rps(w) / usable_capacity`, where `usable_capacity` is as
defined above. A value above 1.0 means the platform is oversold relative
to its headroom-adjusted capacity.

### `fair_share_allocation(w) -> dict[str, float]`

The weighted **max-min fair share** of `usable_capacity` across tenants,
by **progressive filling** (this is the standard water-filling algorithm
for weighted max-min fairness -- look it up under that name or under
"weighted max-min fair share allocation" if the steps below are unclear).
Spelled out exactly, because this is the one place a slightly-different
but plausible-looking algorithm gives a different answer:

1. Let `remaining_capacity = usable_capacity` and `active` = the set of
   all tenant ids.
2. Compute `total_weight = sum(weight[t] for t in active)`. For every
   tenant `t` in `active`, compute its **round share**:
   `share[t] = remaining_capacity * weight[t] / total_weight`.
3. A tenant is **satisfied this round** if `share[t] >= demand[t]`
   (exact comparison -- a tie, `share[t] == demand[t]`, counts as
   satisfied, not unsatisfied).
4. **If no tenant in `active` is satisfied this round:** the fixed point
   has been reached. Every tenant still in `active` gets `allocation[t] =
   share[t]` (its current round share, which is below its demand -- this
   is the leftover capacity split in proportion to weight among the
   tenants that could not be fully satisfied), and the algorithm stops.
5. **Otherwise:** every tenant satisfied this round gets `allocation[t] =
   demand[t]` (exactly its demand, not its round share -- it does not
   receive more than it asked for). Subtract each such `demand[t]` from
   `remaining_capacity`, remove those tenants from `active`, and go back
   to step 2 with the shrunk `active` set and the shrunk
   `remaining_capacity`. (The leftover capacity freed up by satisfying the
   "cheap" tenants is what gets redistributed, proportional to weight,
   among the tenants still unsatisfied -- iterated to a fixed point.)
6. The loop always terminates: whenever step 5 runs, at least one tenant
   leaves `active`, and there are finitely many tenants, so the loop
   either reaches step 4's fixed point or empties `active` entirely.

Return `{tenant_id: allocation[tenant_id]}` for every tenant.

### `unsatisfied_tenants(w) -> list[str]`

The sorted (ascending, lexicographic) list of tenant ids for which
`fair_share_allocation(w)[t] < demand[t]` (strict less-than -- a tenant
allocated exactly its demand is satisfied, not unsatisfied).

### `tenant_monthly_cost_usd(w) -> dict[str, float]`

The infrastructure cost attributed to each tenant at its **allocated**
rate (`fair_share_allocation(w)[t]`, not its raw demand -- a tenant is
billed for what it actually gets served). For each tenant:

- `monthly_requests = allocated_rps * w["seconds_per_month"]`
- `request_cost = (monthly_requests / 1000) * w["cost_per_1k_requests_usd"]`
- `egress_gb = (monthly_requests * avg_response_kb) / 1_000_000`
- `egress_cost = egress_gb * w["cost_per_gb_egress_usd"]`
- `storage_cost = storage_gb * w["cost_per_gb_month_storage_usd"]`
  (the tenant's existing storage footprint, independent of its allocated
  request rate)
- `total_cost = request_cost + egress_cost + storage_cost`

Return `{tenant_id: total_cost}`.

### `tenant_monthly_margin_usd(w) -> dict[str, float]`

`plan_price_usd_month - tenant_monthly_cost_usd(w)[t]` for each tenant.
Can be negative (a tenant costing more than it pays).

### `capacity_rps_for_slo(w) -> float`

The `platform_capacity_rps` value that would make today's total demand
exactly fill `usable_capacity` at the target utilization -- i.e. the
capacity at which `overcommit_ratio` would be exactly 1.0 without changing
anything else:

`total_demand_rps(w) / w["target_utilization"]`

### `max_tenants_at_current_capacity(w) -> int`

How many more tenants "shaped like the average of today's tenants" fit
before usable capacity would be exceeded:

- `avg_tenant_demand = total_demand_rps(w) / len(w["tenants"])`
- `headroom = usable_capacity - total_demand_rps(w)`
- If `headroom <= 0`, the answer is `0` (the platform is already at or
  past its SLO-headroom limit -- it does not fit any more, and strictly
  speaking is already oversold; see `overcommit_ratio`).
- Otherwise, the answer is `floor(headroom / avg_tenant_demand)` as a
  plain `int`.

## Completion criteria

From the module root (`17-system-design/`):

```bash
uv run python 04-multi-tenant-platform/tests/validate.py
```

Prints `PASSED` on success, or a single `NOT PASSED: <reason>` line and a
non-zero exit code otherwise -- including while `src/estimate.py` still
raises `NotImplementedError` or `DESIGN.md` still has `[fill in ...]`
placeholders.

The validator calls every `src/estimate.py` function against the shipped
`workload.json` plus several perturbed variants it builds in memory, and
compares each result to its own independent recomputation of the formulas
above. It also checks `DESIGN.md` structurally: every required section
present and long enough, no leftover placeholders, the design grounded in
concrete mechanisms (not just abstractions), quantitative claims present,
and `### Q1`..`### Q8` under `## Hostile Review` genuinely answered rather
than restated.

## Estimated evenings

1

## Topics to read up on

- Max-min fairness and weighted max-min fair share
- Weighted fair queueing
- Admission control and overcommit in multi-tenant systems
- Noisy-neighbour isolation (cgroups/cgroup v2 analogues at the
  request-routing layer: rate limiting, token buckets, circuit breakers)
- Cost attribution / showback vs. chargeback
- Tenant isolation models (shared-everything vs. shared-nothing vs.
  hybrid/pool-per-tier)
