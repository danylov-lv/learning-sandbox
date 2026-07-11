# Module 09 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
exact schema, seed distributions, RNG draw order, ground-truth semantics,
the pruning-proof mechanism, benchmark methodology, and the dedup fixture
contract every task and validator depends on.

This file is the shared contract for every agent working on this module
(infra, generator, task authors, validators). If you change something here,
regenerate and reverify and update every consumer in the same change.

## Stack

- **clickhouse** `clickhouse/clickhouse-server:24.8` (LTS). DB
  `price_history`, user/password `sandbox`/`sandbox`. HTTP host port `8309`
  (`SANDBOX_09_CH_HTTP_PORT`, container 8123), native TCP `9309`
  (`SANDBOX_09_CH_NATIVE_PORT`, container 9000). `ulimits.nofile` raised to
  262144 (ClickHouse opens many files). `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1`
  so the sandbox user can manage grants. clickhouse-connect talks over HTTP,
  so the harness always uses the HTTP port; the native port is exposed for
  `clickhouse-client` / external tools only.
- **postgres** `postgres:16`. DB `price_history`, user/password
  `sandbox`/`sandbox`. Host port `54309` (`SANDBOX_09_PG_PORT`). Schema
  `price_history` created by `docker/pg-init.sql` (and defensively by
  `generate.py`).

Healthchecks: ClickHouse `wget --spider http://localhost:8123/ping`;
Postgres `pg_isready`. Both reach healthy in a few seconds.

## Fact table schema

One table, `observations`, denormalized (category carried on every row — no
join needed for the analytical queries this module studies).

### Postgres — `price_history.observations`

```sql
CREATE TABLE price_history.observations (
    observation_id BIGINT PRIMARY KEY,
    product_id     INTEGER NOT NULL,
    seller_id      INTEGER NOT NULL,
    category       TEXT NOT NULL,
    currency       TEXT NOT NULL,
    price          NUMERIC(12, 2) NOT NULL,
    in_stock       BOOLEAN NOT NULL,
    scraped_at     TIMESTAMP NOT NULL
);
```

**Deliberately index-light: only the PK on `observation_id`.** No index on
`category`, `scraped_at`, `product_id`, or anything the benchmark query
touches. This is intentional so task 05 (postgres-vs-clickhouse-50m) is a
fair "OLTP row store, no analytical indexing vs a columnar engine with a
sparse index" contrast — the point is the *storage model*, not who indexed
harder. If a future task wants to show what a covering index does to the
Postgres side, it should add it explicitly and measure, not bake it in here.

### ClickHouse — `price_history.observations_raw`

```sql
CREATE TABLE price_history.observations_raw (
    observation_id UInt64,
    product_id     UInt32,
    seller_id      UInt32,
    category       LowCardinality(String),
    currency       LowCardinality(String),
    price          Float64,
    in_stock       UInt8,
    scraped_at     DateTime
)
ENGINE = MergeTree
ORDER BY (category, product_id, scraped_at)
```

**`ORDER BY (category, product_id, scraped_at)` rationale.** In a MergeTree
the `ORDER BY` *is* the (sparse) primary index: data is physically sorted by
this tuple and ClickHouse stores one index mark per granule (8192 rows by
default). A `WHERE` that constrains a leading prefix of the ORDER BY lets
ClickHouse skip whole parts/granules (part pruning) instead of scanning the
table. Leading with the low-cardinality `category` makes the per-category
analytical queries (the module's bread and butter) prune hard; `product_id`
second lets "one product's history" queries prune within a category;
`scraped_at` last gives time-range locality within a product. `category` and
`currency` are `LowCardinality(String)` (8 and 3 distinct values) — dictionary
encoded, cheap to filter and group.

**Price is `Float64` in ClickHouse and Parquet, `NUMERIC(12,2)` in
Postgres.** Prices are generated rounded to 2 decimals, so Float64 carries
them exactly at this magnitude; aggregate cross-checks against ground truth
(itself a numpy float sum) and across engines use a small rounding tolerance,
never exact-decimal equality. Postgres keeps `NUMERIC(12,2)` because that's
the idiomatic money type for the row-store baseline. (`observations_raw` is
the *raw* landing table; the ReplacingMergeTree / MV / TTL tasks build their
own engines on top — hence the `_raw` suffix.)

### Parquet lake — `data/parquet/category=<x>/part-*.parquet`

Hive-partitioned by `category` (so the partition column lives in the path,
not the file). Written with `pyarrow.dataset.write_dataset(...,
partitioning=["category"], partitioning_flavor="hive")`. DuckDB reads it via
`read_parquet(parquet_glob(), hive_partitioning=true)`, which re-exposes
`category` as a column. This is the input for the DuckDB tasks (06, 07) —
zero server, query files directly. Same 8 columns as ClickHouse; `price`
`double`, `scraped_at` `timestamp[s]`.

## Seeded corpus (deterministic, seed 90909)

`generate.py`, one `np.random.default_rng(90909)` stream. `SCALE` (env,
default `1.0`) scales `n_observations = round(50_000_000 * SCALE)`,
`n_products = round(300_000 * SCALE)`, `n_sellers = round(800 * SCALE)` (each
floored at 1). Fully vectorized numpy — no row-by-row creation loops (the
only per-row loops are in the DB *load* path, which is allowed).

Time window: 180 days ending 2025-06-30 (fixed). `date_start` = 2025-01-02,
`n_days` = 180, second resolution.

### Draw order (DO NOT REORDER without regenerating everything)

Product universe (size `n_products`):
- **U1** `product_category_idx = rng.choice(8, size=n_products, p=cat_w)` —
  Zipf category popularity, `w_rank ∝ 1/rank^1.1` over the 8 categories
  `[electronics, home-goods, kitchen, toys, sporting-goods, office-supplies,
  beauty, apparel]` (most→least). A product's category never changes.
- **U2** `popularity_rank = rng.permutation(n_products) + 1`; per-product
  offer weight `∝ 1/rank^1.07`, renormalized (mild Zipf — popular products
  get more observations).
- **U3** `z_base = rng.normal(size=n_products)` → per-product base log-price
  `= ln(median_cat) + sigma_cat * z_base`, using the per-category
  `(median, sigma)` profile (electronics 120/0.9 … office-supplies 15/0.5).
- **U4** `drift_slope = rng.normal(0, 0.15, n_products)` — per-product price
  drift over the window.

Observations (size `n_observations`):
- **O1** `product_id = rng.choice(1..n_products, size=N, p=pop_weight)` (Zipf).
- **O2** `seller_id = rng.integers(1, n_sellers+1, size=N)` (uniform).
- **O3** `currency_idx = rng.choice(3, size=N, p=[0.60,0.25,0.15])` (USD/EUR/GBP).
- **O4** `in_stock = rng.random(N) < 0.85`.
- **O5** `day = rng.choice(180, size=N, p=day_weights)` — mild daily
  cyclicality (weekends ×1.15, gentle upward trend), so per-day counts vary.
- **O6** `second = rng.integers(0, 86400, size=N)` (within-day offset).
- **O7** `noise = rng.normal(0, 0.05, size=N)` (per-observation log jitter).

Price: `price = round(exp(log_base[pid] + drift_slope[pid]*day_norm +
noise), 2)`, clipped to ≥ 0.5, where `day_norm = (day - 89.5)/90 ∈ [-1,1]`.
This gives each product a realistic price *history* (a log-linear drift over
the 180 days — a vectorized stand-in for a per-product random walk — plus
per-scrape jitter), not a constant price. `scraped_at = date_start + day*1d
+ second*1s`.

Natural key `(product_id, seller_id, scraped_at)` is effectively unique in
the base corpus (second resolution × 300k products × 800 sellers over 180
days makes collisions negligible). The base corpus is clean; the dedup task
(03) injects its own duplicates via `build_duplicate_batch` — this table is
never pre-duplicated.

## `data/ground-truth.json` (committed answer key)

Computed entirely in numpy (`_ground_truth`), independent of any DB, so it's
the objective reference every validator compares live query results against.
**The committed file is at SCALE=1.0 (50M rows).** Top-level keys:

- `seed`, `scale`, `n_observations`, `n_products`, `n_sellers`,
  `categories` (list of 8), `date_start`, `date_end`, `n_days`
- `row_counts`: `{"observations": N}`
- `price_sum` (total, round 2), `in_stock_count`,
  `distinct_products_with_observations`
- `per_category`: `{cat: {count, price_sum(round2), avg(round4)}}` — all rows
- `per_category_instock`: same shape, filtered `in_stock=true`. **This is the
  canonical pg-vs-ch BENCHMARK QUERY answer**: per-category count + avg over
  in-stock rows.
- `per_day_count`: `{"YYYY-MM-DD": count}` (180 entries)
- `daily_category`: `{"YYYY-MM-DD|category": {count, price_sum(round2)}}` —
  the MV task's (02) expected target content (1440 non-empty entries at scale
  1.0). Only cells with count > 0 are emitted.
- `top_sellers_by_count`: top 10 `[[seller_id, count], ...]`, descending.

At SCALE=1.0: `n_observations=50000000`, `price_sum=4556165751.93`,
`in_stock_count=42496895`, `per_category[electronics]={count:22588593,
price_sum:3406338747.39, avg:150.7991}`.

### How ground truth stays coherent with the live stack

`generate.py` at scale `X` loads all three sinks *and* rewrites
ground-truth.json to scale `X`. The committed file is 50M; the live stack in
this box was loaded at a light scale for verification. A task-authoring /
verification wave should: run `SCALE=x generate.py` (stack + ground truth now
agree at scale x), author/verify, then `GROUND_TRUTH_ONLY=1 generate.py`
(SCALE=1.0) to restore the committed 50M answer key before committing.

## The pruning proof — `harness/common.py:ch_read_rows`

The structural (non-timing) check the MergeTree tasks grade against.
Mechanism: run the query with a freshly generated `query_id` (passed as a
ClickHouse URL param via clickhouse-connect `settings={"query_id": ...}`),
`SYSTEM FLUSH LOGS`, then read `read_rows` from the `system.query_log` row for
that exact `query_id` where `type='QueryFinish'`. `read_rows` = rows
ClickHouse actually scanned off disk (from granules it could not prune), NOT
rows returned.

**Gotcha for task authors:** `SELECT count()` is answered from part metadata
and reads ~0 rows — it is a useless "full scan" baseline. Use an aggregate
that forces a real column read, e.g. `SELECT sum(price) ...`. Verified live
at SCALE=0.01: `sum(price)` full scan read 500000 rows; the same with
`WHERE category=<c> AND product_id < 50` read 8192 (one granule) — pruned <
full, proving the sparse primary index skips granules.

## Benchmark methodology (task 05, 07)

Two-part, per repo convention:
1. **Correctness is primary** — the query result must match ground truth
   (`per_category_instock`) within rounding tolerance. A fast wrong answer
   fails.
2. **Timing is relative** — never an absolute threshold. A baseline step runs
   first and writes its measured seconds to a gitignored `*-local.json` via
   `write_baseline`; later comparisons read it back with `read_baseline` and
   assert a *ratio* (e.g. ClickHouse ≤ some fraction of Postgres on the same
   box), so results are portable across machines. `time_it(fn, ...)` returns
   `(result, seconds)`.

## Dedup fixture — `generate.py:build_duplicate_batch(seed, n)`

Pure function (numpy only, no DB), for the ReplacingMergeTree task (03).
Returns a list of `n` row dicts in which the natural key
`(product_id, seller_id, scraped_at)` collides across multiple rows, each
carrying a distinct `version` and matching `ingested_at`:

```python
{"product_id": int, "seller_id": int, "scraped_at": datetime,
 "category": str, "currency": str, "price": float, "in_stock": bool,
 "version": int, "ingested_at": datetime}
```

Contract: group by the natural key; within each group the **highest
`version`** is the survivor a `ReplacingMergeTree(version)` keeps after a
`FINAL`/merge, and its `price`/`in_stock` are that key's current values.
`ingested_at` increases with `version`, so ordering by either yields the same
winner. Rows are returned in ingest order (ascending `ingested_at`), NOT
grouped by key, so a naive insert reproduces a realistic out-of-order
duplicate stream. `n_keys ≈ n // 3` (about 3 versions per key on average).
`product_id`/`seller_id` are drawn from the SCALE=1.0 universe
(1..300000 / 1..800); `category = CATEGORIES[product_id % 8]` (stable per
product); prices are a generic `lognormal(median=40, sigma=0.6)`,
deliberately category-agnostic — a synthetic dedup stream, not a second
realistic corpus (same spirit as module 08's `build_workload`).

## Verified live (wave-1 infra check)

See `notes-infra.md` for the exact commands, versions, and timings. Summary:
both services healthy; `SCALE=0.01 generate.py` loaded Postgres (500k),
ClickHouse (500k), and the Parquet lake in ~8s; Postgres / ClickHouse /
DuckDB counts all == 500000 and matched ground truth; `price_sum` matched
across pg, ch, and ground truth exactly (36780355.61); the
`per_category_instock` benchmark answer for `electronics` matched exactly
(count 135087, avg 134.6063); `ch_read_rows` proved pruning (500000 full vs
8192 pruned); and `GROUND_TRUTH_ONLY=1 SCALE=1.0 generate.py` wrote the
committed 50M answer key in ~14s (numpy only, no DB).
