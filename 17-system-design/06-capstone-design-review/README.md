# 06 — Capstone: price intelligence platform design review

## Backstory

You have spent two years scraping the web for a living: requests and
BeautifulSoup, then Scrapy spiders running as producer/consumer pairs
over RabbitMQ on Kubernetes, backend work in Django, FastAPI and NestJS.
Along the way you have designed capacity for a 10k-site crawl, sized five
years of price history, built a delivery pipeline against client SLAs,
carved a multi-tenant platform out of shared infrastructure, and written
a postmortem for the day one of those systems fell over.

Now your director asks you to do the thing you have actually been doing
piecemeal, as one document: design the whole price intelligence platform,
end to end, and defend it in front of a design review panel that will not
be kind. Acquisition from thousands of hostile sites. A quality and
contract layer between what gets scraped and what a client is allowed to
see. Five years of historical storage with an analytical serving layer on
top. Per-client delivery under contractual SLAs. Multi-tenancy across
hundreds of paying customers sharing the same fleet. And the operational
envelope that keeps it alive at 3 a.m. — SLOs, alerting, on-call, and a
cost model the finance team will actually believe.

This is the capstone. It is not a bigger version of tasks 01–05; it is
the same system those five tasks looked at from different angles, now
assembled into one design review packet, sized with one capacity model,
and defended under hostile questioning.

## What's given

- `workload.json` — the platform-wide parameters: URL counts and
  freshness tiers, fetch and parse cost, storage row size/retention/
  compression, hot-tier window, analytical query volume, client tiers
  with SLA deadlines and per-tenant record volumes, tenant count, unit
  costs, target utilization, peak factor, and the 10x growth multiplier.
  You do not choose these numbers — you size a design against them.
- `src/estimate.py` — 12 function stubs, each `raise NotImplementedError`,
  each with a docstring stating its contract (inputs, output units,
  rounding rule). The formulas themselves live in this README's "Capacity
  model contract" section below, not in the code.
- `DESIGN.md`, `REVIEW.md`, `docs/adr-001.md`, `docs/adr-002.md`,
  `docs/adr-003.md` — unfilled templates. Every required section is
  present as a heading so the validators can discover the shape of the
  document; every body is a `[fill in: ...]` placeholder.
- `HOSTILE-REVIEW.md` — the twelve questions a skeptical panel would ask
  this design. `DESIGN.md`'s final `## Hostile review responses` section
  has one `### Q1` .. `### Q12` subsection per question, for your answers.
- `hints/` — three hints, direction to concrete mechanism, if you get
  stuck on either the design or the arithmetic.
- `NOTES.md` — the standard "what I learned / gotchas / open questions"
  template.

`../harness/common.py` is shared infrastructure used by every validator
in this module. Read it if you are curious how grading works; do not
edit it.

## What's required, by checkpoint

### CP1 — requirements and capacity

Fill in, in `DESIGN.md`:

- `## Problem statement and scope` — what this system is and, just as
  importantly, what it explicitly does not do.
- `## Requirements, SLIs and SLOs` — functional requirements, and a set
  of SLIs with numeric SLO targets (freshness, availability, delivery
  latency, data quality) that a client contract could actually reference.
- `## Workload characterization` — read `workload.json` and describe the
  shape of the load it implies: tier skew, client-tier skew, tenant
  concentration, the awkward parts.
- `## Capacity model` — walk through what `src/estimate.py` computes and
  why those are the numbers that matter (fleet size, egress, storage,
  peak headroom).
- `## Cost model` — the cost breakdown by component and where the money
  actually goes.

Implement every function in `src/estimate.py` per the "Capacity model
contract" section below.

### CP2 — architecture, data flow and failure

Fill in, in `DESIGN.md`:

- `## Architecture` — the system's major pieces and how they connect.
- `## Component responsibilities` — what each piece owns and, critically,
  does NOT own.
- `## Data flow and contracts` — how a price fact moves from a hostile
  site to a client's delivered record, and what contract (schema,
  validation, versioning) guards each handoff.
- `## Storage and serving layout` — how the hot/cold tiers and the
  analytical serving layer are actually laid out (partitioning, indexing,
  file/table format, what serves the `analytics.queries_per_day` load).
- `## Multi-tenancy and isolation` — how tenants share the fleet without
  sharing each other's data or blast radius.
- `## Failure modes and blast radius` — for each major component, what
  happens when it fails and who is affected.
- `## Degradation ladder` — under overload, what gets shed first, what
  second, what third, and what is never shed.
- `## Evolution at 10x` — what changes, structurally, at 10x the current
  volume (not just "add more machines").

Write three ADRs in `docs/adr-001.md`, `docs/adr-002.md`, `docs/adr-003.md`,
each following the fixed template (see below). Each ADR must record a
genuinely contested choice in this design and argue at least two rejected
alternatives fairly — not straw men you set up to knock down.

### CP3 — defence

Fill in, in `DESIGN.md`:

- `## Hostile review responses` — with `### Q1` through `### Q12`, one
  per question in `HOSTILE-REVIEW.md`, each answered on its own merits
  (not a restatement of the question, not a placeholder).
- `## Risk register` — the concrete risks in this design, not generic
  ones, each with what would catch it and what you would do about it.

Fill in `REVIEW.md`: name the three weakest parts of your own design —
`### Weakness 1`, `### Weakness 2`, `### Weakness 3` — and for each, what
evidence would change your mind about it.

CP3 also re-runs CP1's and CP2's validators as subprocesses. If either
has regressed since you last had it green, CP3 fails too.

## ADR template

Each of `docs/adr-001.md`, `docs/adr-002.md`, `docs/adr-003.md` must use
this exact section shape:

```markdown
# ADR-00N: <title>

## Context

## Decision

## Alternatives considered

## Consequences
```

`## Alternatives considered` must list at least two rejected alternatives
as bullet points (`- ` or `* `), each with a real reason it was rejected
— a real trade-off, not "it was worse."

## Capacity model contract

Unit conventions used throughout, pinned so your arithmetic and the
validator's independent recomputation agree:

- 1 day = 1440 minutes = 86400 seconds.
- 1 month = 30 days (for every "monthly" quantity in this task).
- 1 year = 365 days (for `storage.retention_years`).
- 1 GB = 1e9 bytes (decimal gigabytes, not GiB).

**Logical daily refresh volume** (used by several functions below):

```
daily_new_rows = sum over each tier t in acquisition.tiers of:
    acquisition.total_tracked_urls * t.fraction * (1440 / t.refresh_interval_minutes)
```

This is the count of successful, logical price-point refreshes per day —
one per URL per cadence, independent of retries.

**Retry overhead model** (a deliberate approximation, not a full geometric
retry simulation — state this in your design doc if you rely on it):

```
expected_attempts_per_url = 1 + (1 - acquisition.success_rate_first_attempt) * (acquisition.max_attempts - 1)
daily_new_rows_effective = daily_new_rows * expected_attempts_per_url
```

**`required_fetch_capacity_per_sec(workload)`**

```
required_fetch_capacity_per_sec = daily_new_rows_effective / 86400
```

Float, no rounding.

**Per-pod fetch throughput** (not itself an exported function, used by
`fleet_size` and `utilization_at_peak`):

```
per_pod_capacity = acquisition.worker_concurrency_per_pod * 1000 / acquisition.avg_fetch_latency_ms
```

(fetches/second/pod — each concurrent slot completes one fetch every
`avg_fetch_latency_ms` milliseconds.)

**`fleet_size(workload)`**

```
fleet_size = ceil( required_fetch_capacity_per_sec / (per_pod_capacity * ops.target_utilization) )
```

Int, rounded UP to the next whole pod.

**Egress volumes** (used by `monthly_egress_gb` and `monthly_cost_by_component`):

```
fetch_egress_bytes_per_month = daily_new_rows_effective * 30 * acquisition.avg_fetch_bytes

delivery_records_per_month = sum over each client tier c in clients.tiers of:
    clients.tenant_count * c.weight * c.records_per_delivery * c.deliveries_per_day
  , then that whole sum * 30

delivery_egress_bytes_per_month = delivery_records_per_month * storage.avg_row_bytes_normalized
```

**`monthly_egress_gb(workload)`**

```
monthly_egress_gb = (fetch_egress_bytes_per_month + delivery_egress_bytes_per_month) / 1e9
```

Float, no rounding.

**`storage_hot_bytes(workload)`**

```
storage_hot_bytes = round(
    daily_new_rows * storage.hot_tier_window_days * storage.avg_row_bytes_normalized
    / storage.hot_compression_ratio
)
```

Int, rounded to the nearest whole byte (Python's `round`, banker's
rounding — the validator uses `rel_tol=1e-6` so this never matters in
practice at these magnitudes).

**`storage_cold_bytes(workload)`**

```
cold_days = storage.retention_years * 365 - storage.hot_tier_window_days

storage_cold_bytes = round(
    daily_new_rows * cold_days * storage.avg_row_bytes_normalized
    / storage.cold_compression_ratio
)
```

Int, rounded to the nearest whole byte.

**`monthly_cost_by_component(workload)`** — dict with keys `"compute"`,
`"proxy"`, `"egress"`, `"storage"`:

```
compute = fleet_size * 24 * 30 * cost.compute_usd_per_pod_hour
proxy   = (fetch_egress_bytes_per_month / 1e9) * cost.proxy_usd_per_gb
egress  = (delivery_egress_bytes_per_month / 1e9) * cost.egress_usd_per_gb
storage = (storage_hot_bytes / 1e9) * cost.storage_hot_usd_per_gb_month
        + (storage_cold_bytes / 1e9) * cost.storage_cold_usd_per_gb_month
```

Each value a float, no rounding. `fleet_size`, `storage_hot_bytes` and
`storage_cold_bytes` here are the same values the eponymous functions
return (computed against the same workload).

**`total_monthly_cost(workload)`**

```
total_monthly_cost = compute + proxy + egress + storage
```

(the sum of every value in `monthly_cost_by_component(workload)`.) Float,
no rounding.

**`cost_per_delivered_record(workload)`**

```
cost_per_delivered_record = total_monthly_cost / delivery_records_per_month
```

Float, no rounding.

**`peak_delivery_rate(workload)`**

```
peak_delivery_rate = (delivery_records_per_month / (30 * 86400)) * ops.peak_hour_factor
```

Float, records/second, no rounding.

**`utilization_at_peak(workload)`**

```
utilization_at_peak = (required_fetch_capacity_per_sec * ops.peak_hour_factor)
                       / (fleet_size * per_pod_capacity)
```

Note the denominator uses raw fleet capacity (`fleet_size * per_pod_capacity`),
NOT scaled by `target_utilization` again — `target_utilization` already
went into sizing `fleet_size`. Float, dimensionless. Values above 1.0 are
valid and expected to show up under this workload; do not clamp.

**10x growth workload** (used by the last two functions): the derived
workload identical to the input except:

```
grown.acquisition.total_tracked_urls = workload.acquisition.total_tracked_urls * workload.ops.growth_multiplier_10x
grown.clients.tenant_count           = workload.clients.tenant_count * workload.ops.growth_multiplier_10x
```

Every other field is unchanged. Build this derived dict in memory; never
write it to disk.

**`fleet_size_at_10x(workload)`**

```
fleet_size_at_10x = fleet_size(grown)
```

Same formula as `fleet_size`, evaluated against the grown workload. Int,
rounded up.

**`storage_and_cost_at_10x(workload)`** — dict with keys `"storage_bytes"`,
`"monthly_cost"`:

```
storage_bytes = storage_hot_bytes(grown) + storage_cold_bytes(grown)
monthly_cost  = total_monthly_cost(grown)
```

`storage_bytes` an int, `monthly_cost` a float, no further rounding beyond
what the component formulas already specify.

## Completion criteria

Run each from the **module root** (`17-system-design/`):

```bash
uv run python 06-capstone-design-review/tests/validate_cp1.py
uv run python 06-capstone-design-review/tests/validate_cp2.py
uv run python 06-capstone-design-review/tests/validate_cp3.py
```

or all three in sequence:

```bash
uv run python 06-capstone-design-review/tests/validate.py
```

Each prints `PASSED` and exits 0 when its gate is satisfied, or
`NOT PASSED: <reason>` and exits 1 otherwise. The capstone is done when
all three checkpoints — and therefore `validate.py` — print `PASSED`.

## Estimated evenings

2

## Topics to read up on

- Back-of-the-envelope capacity estimation and Little's Law
- SLI/SLO design, and what makes an SLO measurable vs. aspirational
- Architecture Decision Records and how to argue rejected alternatives
  fairly instead of as straw men
- Blast radius and failure domain analysis
- Load shedding and graceful degradation ladders
- Multi-tenancy isolation models: noisy-neighbor containment, quotas,
  shared-fleet vs. dedicated-fleet trade-offs
- Cold/hot data tiering and columnar analytical storage
- Cost modeling for data platforms: unit economics, cost per delivered
  unit, and where estimates typically go wrong by an order of magnitude
