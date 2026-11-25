# 09 — Dedup: Latest Snapshot

## Backstory

The "current price" endpoint that other teams hit is backed by a query that picks the
latest `price_snapshots` row per `(product_id, source_id)`. Someone filed a bug: two
consecutive calls to the endpoint, seconds apart with no new scrape in between,
returned different prices for the same product/source pair. Nothing changed in the
data — the query itself is non-deterministic. The likely cause: whatever "pick the
latest row" logic is in there breaks ties arbitrarily when two snapshots for the same
pair share the same `captured_at`, and depending on physical row order (which
Postgres does not guarantee is stable across query plans), you get one row on one
call and the other row on the next.

You're fixing the dedup logic and proving it's deterministic, then rolling the result
up into a small summary table product management actually wants to look at, instead
of a half-million-row "latest price per pair" dump.

Before you fix it: check whether the trap is even real in this dataset — are there
actually two `price_snapshots` rows sharing the same `(product_id, source_id,
captured_at)`? Report what you find in your own `NOTES.md`. Either way, the
tie-breaker in "What's required" below is mandatory: it's what makes the query
correct *by construction*, whether or not today's data happens to trigger the bug.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency,
  in_stock)`
- `sources(id, name, country, tier, currency)`

## What's required

Step 1 (intermediate, not directly graded): for each `(product_id, source_id)` pair,
determine the single latest snapshot, using this tie-breaker to guarantee
determinism: order by `captured_at` descending, then `id` descending, and take the
first row. Two techniques can produce this — `DISTINCT ON` and a windowed
`ROW_NUMBER()` — pick either, but the tie-breaker must be exactly this one.

Step 2 (graded output): aggregate the latest-snapshot-per-pair result into one row
per `(tier, currency)` — where `tier` and `currency` both come from the snapshot's
source — with columns in this exact order:

- `tier`
- `currency`
- `pair_count` — number of `(product_id, source_id)` pairs in this bucket.
- `avg_latest_price` — average of `price` across those pairs' latest snapshots,
  rounded to 2 decimal places.
- `in_stock_share` — fraction of those pairs whose latest snapshot has
  `in_stock = true`, as a value between 0 and 1, rounded to 4 decimal places.

## Completion criteria

Write your query into `src/query.sql`. From the module root:

```
uv run python validate.py 09
```

Must print `PASSED`.

## Estimated evenings

1

## Topics to read up on

- `DISTINCT ON` in Postgres and how its `ORDER BY` requirement determines which row
  survives
- `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` as the DISTINCT ON alternative,
  and when you'd prefer one over the other
- Why "pick any row" queries without an explicit tie-breaker are undefined behavior,
  not just "unlikely to matter"
- Two-stage query design: a deduplication CTE feeding an aggregation
