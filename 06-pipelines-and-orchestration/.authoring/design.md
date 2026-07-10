# Module 06 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents planted
defects, exact distributions, and ground-truth semantics that the tasks and
validators depend on. Read it afterwards if you want to see how the mess was
built.

This file is the shared contract for every agent working on this module
(generator, docker/infra, Airflow DAGs, dbt models, validators). If you change
a number here, regenerate data and update every consumer in the same change.

## Warehouse

- Postgres, db `pipelines`, user `sandbox`, password `sandbox`.
- Host port `54306`, env override `SANDBOX_06_PORT` (default `54306` if unset).
- Schemas: `staging`, `core`, `mart`, `ops`. (`ops` is for run/audit metadata —
  load watermarks, DAG run logs, dead-letter tables — not business data.)
- This entry has been added to the root `CONVENTIONS.md` ports table.

## Raw data layout

- `06-pipelines-and-orchestration/data/raw/dt=YYYY-MM-DD/prices.ndjson`
- One file per day, `dt=2025-06-01` through `dt=2025-06-14` inclusive (14 days,
  fixed regardless of `SCALE` — `SCALE` only changes volume per day).
- Each line is meant to be one HTTP-scrape event as dumped by an upstream
  scraper: newline-delimited JSON, UTF-8, `\n` line endings.

## Record shape (valid record, pre-drift)

```json
{
  "source_site": "shopnest.example",
  "product_url": "/products/p-03421-kitchen",
  "title": "...",
  "category": "kitchen",
  "price": 34.99,
  "currency": "USD",
  "in_stock": true,
  "scraped_at": "2025-06-03T14:22:07Z"
}
```

Natural dedup key: `(source_site, product_url, scraped_at)`.

## Universe (deterministic, seed 60606)

- `N_PRODUCTS = 8000`, ids `1..8000`.
- 6 fixed source domains (`.example` TLD, not real, deliberately):
  `shopnest.example`, `dealbarn.example`, `cartify.example`,
  `brightbuy.example`, `thriftloop.example`, `primemart.example`.
  Chosen uniformly per record (no skew across sources).
- 12 categories, Zipf-skewed selection weight `w_rank ∝ 1/rank^1.1` (rank 0..11
  in this fixed order, most to least popular): `electronics`, `home-goods`,
  `kitchen`, `toys`, `sporting-goods`, `office-supplies`, `beauty`, `grocery`,
  `pet-supplies`, `tools`, `furniture`, `apparel`.
- Every product is assigned exactly one category at universe-build time, drawn
  with the same category weights (so category sizes are themselves skewed).
- Within a category, product popularity is Zipf: each product gets a
  popularity rank via a random permutation, weight `1/rank^1.2`, renormalized
  within its own category. This weight is used whenever a *fresh* valid
  record needs a product from that category.
- Product `title` is generated once per product via `Faker.catch_phrase()`
  (Faker seeded 60606, drawn in product-id order) and stays fixed forever —
  it does not change across scrapes or drift.
- `product_url = f"/products/p-{product_id:05d}-{category_slug}"` — fixed per
  product, identical regardless of which source scrapes it. This is a
  deliberate simplification: real sites use different URLs for the same
  product, but the module doesn't need that axis of realism.
- Category price profile (lognormal `price = exp(normal(mu, sigma))`, tuned so
  `median = exp(mu)`):

  | category | median | sigma |
  |---|---|---|
  | electronics | 120 | 0.9 |
  | home-goods | 45 | 0.7 |
  | kitchen | 35 | 0.6 |
  | toys | 25 | 0.6 |
  | sporting-goods | 55 | 0.7 |
  | office-supplies | 15 | 0.5 |
  | beauty | 20 | 0.5 |
  | grocery | 8 | 0.4 |
  | pet-supplies | 18 | 0.5 |
  | tools | 40 | 0.7 |
  | furniture | 250 | 0.8 |
  | apparel | 30 | 0.6 |

  `p99 = median * exp(sigma * 2.3263)` (lognormal 99th percentile), computed
  per category at generation time — used as the "absurd price" threshold for
  invalid records (`>= 10x p99`, actual multiplier drawn uniformly in
  `[10, 20)`).
- Currency weights: `USD 0.60`, `EUR 0.25`, `GBP 0.15`, drawn independently per
  record (not tied to source or category).
- `in_stock`: Bernoulli, `P(true) = 0.85`.
- `scraped_at`: uniform random second within `[dt 00:00:00Z, dt+1 00:00:00Z)`.

## Volume

- Target total lines for a day: `T ~ Lognormal(mean=ln(45000 * SCALE), sigma=0.2)`,
  drawn from the module's single seeded `np.random.default_rng(60606)` stream,
  one draw per day in date order. At `SCALE=1.0` this puts the 10th–90th
  percentile of daily line count roughly in the 30k–60k band described in the
  brief. `SCALE` is read from the `SCALE` env var, default `1.0`.

## Composition of a day's file (all counts derived from `T`, rounding first,
## last bucket absorbs the rounding remainder so components sum exactly)

1. `malformed_lines = round(T * 0.004)` — structurally broken lines (poison).
2. `duplicate_lines = round(T * 0.02)` — exact verbatim copies of another line
   generated earlier the same day (line-for-line byte-identical, inserted at a
   random position in the file). Can duplicate either a valid or an invalid
   line, never a malformed line.
3. `base = T - malformed_lines - duplicate_lines` — the count of distinct
   parseable (valid or invalid) records generated before duplication.
4. `invalid_records = round(base * 0.01)` — invalid-but-parseable records (see
   below).
5. `valid_records = base - invalid_records`.
6. `late_arriving_records = round(valid_records * 0.03)` for every day except
   the first (`dt=2025-06-01`, which has no previous day and therefore 0).
   These are a **subset** of `valid_records`, not additive.
7. `fresh_valid_records = valid_records - late_arriving_records`.

So: `total_lines = malformed_lines + duplicate_lines + valid_records + invalid_records`,
and `parseable_records = total_lines - malformed_lines = duplicate_lines + valid_records + invalid_records`.
Validators can check this identity directly against `ground-truth.json`.

## Late-arriving repeats (mechanic, not a defect)

For every day after the first, the generator keeps the previous day's list of
distinct `(source_site, product_id)` pairs that appeared in that day's valid
records. `late_arriving_records` many records are built by sampling from that
pool (uniformly, with replacement) and reusing the same `source_site` and
product identity (hence same category, url, title) but drawing a **new**
`scraped_at` inside the current day, a **new** price (independent lognormal
draw from the same category profile — simulates a re-scrape catching a price
change), a new `in_stock`, and an independent currency draw. Because
`scraped_at` differs from the original day's timestamp, these do not collide
with the dedup key `(source_site, product_url, scraped_at)` — they are
legitimate distinct events, not duplicates. Any incremental/backfill logic
that keys off `product_url + source_site` alone (ignoring `scraped_at`) will
see what looks like an "update"; that's the point of this mechanic.

## Invalid-but-parseable records (~1% of `base`)

Each invalid record starts as an otherwise-normal record, then one field is
corrupted. Reasons are split from `invalid_records` in fixed proportions
`[0.30, 0.30, 0.20, 0.20]` for `[missing_url, bad_price, unknown_currency,
bad_timestamp]` respectively (rounded, `bad_timestamp`'s bucket absorbs the
rounding remainder so the four buckets sum exactly to `invalid_records`):

- `missing_url`: `product_url` is `null` on even-indexed records within the
  bucket, the key is omitted entirely on odd-indexed ones.
- `bad_price`: half negative (`uniform(-500, -1)`), half absurd
  (`category p99 * uniform(10, 20)`). Always emitted as a plain JSON number,
  even on/after the price-string drift date (see below) — invalid records
  never participate in that drift.
- `unknown_currency`: `currency` replaced by one of `XXX`, `ZZZ`, `N/A`, `???`
  (cycled by index within the bucket).
- `bad_timestamp`: `scraped_at` shifted by a random whole number of days in
  `[-5, -1] ∪ [1, 5]` from the record's nominal day, so it lands outside
  `[dt 00:00:00Z, dt+1 00:00:00Z)`.

Invalid records never get `seller_rating` and are never sampled into the
late-arriving pool (that pool is drawn only from valid records).

## Malformed (poison) lines (~0.4% of `T`)

Cycled deterministically by index within the day's malformed count, three
kinds, all guaranteed to fail `json.loads`:

1. Truncated JSON — a valid line's serialized text sliced to a random length
   in `[10, 60)` characters.
2. Dangling-field JSON — `{"source_site": "...", truncated` (an opening object
   that never closes).
3. Non-JSON garbage — the literal prefix `NOT_JSON ` followed by a
   `Faker.sentence()`.

## Schema drift

- **Drift A — additive field.** From `2025-06-10` onward (inclusive), valid
  records (fresh and late-arriving) gain `seller_rating`, a float drawn
  `uniform(1.0, 5.0)`, rounded to 1 decimal. Invalid and malformed lines never
  get it, on any date.
- **Drift B — type change.** From `2025-06-12` onward (inclusive), `price` on
  valid records is emitted as a formatted **string** instead of a JSON number,
  chosen 50/50 per record between two locale styles:
  - Style A (US-ish): symbol prefix + comma thousands + dot decimals, e.g.
    `"$1,299.00"`. Symbol map: `USD -> $`, `EUR -> €`, `GBP -> £`.
  - Style B (EU-ish): dot thousands + comma decimals + trailing currency
    code, e.g. `"1.299,00 EUR"`.
  The record's `currency` field is unaffected by drift and always carries the
  real ISO code. Invalid records' `bad_price` values are always numeric,
  drift or not (see above).
- The two drift dates overlap for `2025-06-12`–`2025-06-14`: those days have
  both `seller_rating` present and `price` as a string.

## `data/ground-truth.json`

Committed to git despite `data/` being otherwise ignored (see module
`.gitignore`) — it's the answer key the generator computes while it plants
data, not something re-derivable by re-parsing, and other agents/tasks need it
without regenerating multi-day NDJSON. Top-level shape:

```json
{
  "seed": 60606,
  "scale": 1.0,
  "days": ["2025-06-01", ..., "2025-06-14"],
  "schema_drift": {"seller_rating_from": "2025-06-10", "price_string_from": "2025-06-12"},
  "constants": {
    "sources": [...6 domains...],
    "categories": [...12 names, in Zipf-rank order...],
    "currency_weights": {"USD": 0.60, "EUR": 0.25, "GBP": 0.15},
    "n_products": 8000
  },
  "per_day": {
    "2025-06-01": {
      "total_lines": int,
      "malformed_lines": int,
      "parseable_records": int,
      "duplicate_lines": int,
      "invalid_records": {
        "total": int,
        "missing_url": int, "bad_price": int,
        "unknown_currency": int, "bad_timestamp": int
      },
      "valid_records": int,
      "late_arriving_records": int,
      "distinct_products_valid": int,
      "has_seller_rating": bool,
      "price_is_string": bool
    },
    ...
  },
  "per_day_currency": {
    "2025-06-01": {"USD": {"count": int, "price_sum": float}, "EUR": {...}, "GBP": {...}},
    ... all 14 days, drift days included ...
  },
  "global": {
    "distinct_source_product_pairs": int,
    "per_category_valid_counts": {"electronics": int, ...},
    "mart_reference": {
      "2025-06-01": {"USD": {"count": int, "price_sum": float}, "EUR": {...}, "GBP": {...}},
      ...
      "2025-06-12": {"USD": {"count": int}, "EUR": {"count": int}, "GBP": {"count": int}}
    }
  }
}
```

Field notes:
- `distinct_products_valid` (per day): distinct `product_id` among that day's
  valid records (fresh + late-arriving), i.e. distinct products *active* that
  day, not cumulative.
- `global.distinct_source_product_pairs`: distinct `(source_site,
  product_url)` pairs seen in valid records across all 14 days (dedup counted
  once no matter how many times/days scraped).
- `global.per_category_valid_counts`: sum of valid records per category across
  all 14 days.
- `global.mart_reference`: per day, per currency, over **valid records only**.
  For days before the price-string drift (`< 2025-06-12`): `count` and
  `price_sum` (sum of the numeric `price`). From `2025-06-12` onward: `count`
  only — the generator deliberately withholds a numeric answer key for those
  days because `price` is a locale-formatted string there; parsing it
  correctly is the task's point, not something to hand the learner ground
  truth for.
- `per_day_currency` (top-level, added for price-normalization validators):
  per day, per currency, over **valid records only** — `count` plus
  `price_sum`, where `price_sum` is the sum of each record's TRUE planted
  numeric price rounded to 2 decimals, the sum itself then rounded to 2
  decimals. Unlike `global.mart_reference`, this covers ALL 14 days including
  the drift days (`>= 2025-06-12`): the generator records the numeric it
  planted *before* string formatting, so validators can check a learner's
  parse-and-normalize output against it (recommended tolerance 0.02).
  Exact-round-trip guarantee: on drift days the formatted string encodes
  exactly the same 2-decimal numeric as the planted value — both
  `round(price, 2)` and the `"%,.2f"`-style formatting apply round-half-even
  to the same float, so parsing `"$1,299.00"` / `"1.299,00 EUR"` back yields
  the planted 2-decimal value exactly. Verified empirically at SCALE=1.0:
  re-parsing every drift-day price string and re-summing reproduces
  `per_day_currency` counts exactly and sums within 0.02, with zero strings
  deviating from an exact 2-decimal value. Pre-drift days agree exactly with
  `global.mart_reference` (which remains unchanged for compatibility).
  Consistency invariant: per day, `sum(count over currencies) ==
  per_day.<day>.valid_records`.

## Alerts sink (docker agent owns the sink implementation)

- Contract: alerting code (Airflow tasks, dbt hooks, whatever) POSTs a JSON
  body to `http://alert-sink:8000/alert`.
- The sink appends each POST body as one NDJSON line to
  `data/alerts/alerts.ndjson` on the host (bind-mounted from the container).
- `harness/common.py` exposes `read_alerts()` to read that file from the host
  side for validators.
- No schema is imposed on the alert body by this contract — whatever a task's
  DAG sends is whatever gets appended. Tasks that check alert content should
  check for the specific keys they know they sent.

## Ports table addition

Added to root `CONVENTIONS.md`:

| Module | Service | Host port | Env var |
|---|---|---|---|
| 06-pipelines-and-orchestration | Postgres | 54306 | `SANDBOX_06_PORT` |
