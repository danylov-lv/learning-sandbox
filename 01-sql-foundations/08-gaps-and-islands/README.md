# 08 — Gaps and Islands

## Backstory

Ops wants leverage in an upcoming supplier renegotiation: which (product, source)
pairs go out of stock for the longest continuous stretches? A single-snapshot
`in_stock = false` doesn't mean much — scrapers sample every few hours and a product
can flicker in and out. What ops actually cares about is *runs*: consecutive
snapshots for the same product on the same source that are all out of stock, back to
back, with nothing in between. The longest of those runs are the ones worth putting
in front of a supplier.

You've hit this shape of problem before in log analysis — "how long was service X
down" from a stream of health-check pings is the same pattern. Here it's stock-outs
instead of downtime pings, but the SQL technique is identical.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency,
  in_stock)` — one row per scrape observation. For a given `(product_id, source_id)`
  pair, snapshots are irregular in spacing but ordered by `captured_at`.
- "Continuous" is defined purely in terms of the *scrape sequence* for that pair, not
  wall-clock time: a run is a maximal set of consecutive-in-sequence snapshots (for
  the same product_id + source_id) that all have `in_stock = false`. Gaps in
  wall-clock time between two false snapshots do not break the run as long as no
  `in_stock = true` snapshot sits between them in the sequence.

## What's required

The top 25 longest out-of-stock streaks across the whole dataset, one row per streak,
columns in this exact order:

- `product_id`
- `source_id`
- `streak_snapshots` — number of consecutive `in_stock = false` snapshots in the run.
- `streak_start` — `captured_at` of the first snapshot in the run.
- `streak_end` — `captured_at` of the last snapshot in the run.

Tie-breakers, applied in order, to make the top-25 cut and the row order fully
deterministic: `streak_snapshots` descending, then `product_id` ascending, then
`source_id` ascending, then `streak_start` ascending. (The validator sorts rows
canonically before comparing, so your query's `ORDER BY` doesn't need to match this
exactly — but your `LIMIT 25` must select the *same 25 rows*, so get the tie-breaker
chain right before you limit.)

## Completion criteria

Write your query into `src/query.sql`. From the module root:

```
uv run python validate.py 08
```

Must print `PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- The gaps-and-islands SQL pattern
- Window functions: `ROW_NUMBER()` vs `LAG()`/`LEAD()`, and how partitioning
  interacts with ordering
- The "row-number-difference" trick: taking two row numbers computed over different
  partitions and using their difference as a group identifier
- Why a naive `LAG()`-based "is this row different from the previous row" flag is not
  by itself a group id — you still need to turn flags into groups
