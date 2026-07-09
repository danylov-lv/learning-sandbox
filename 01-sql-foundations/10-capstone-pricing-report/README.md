# 10 — Capstone: Quarterly Pricing Report

## Backstory

Once a quarter, the CEO reads a one-page "market pricing report": for each top-level
product category, how many products are you tracking, how much data backs the
number, what's the typical price in USD, how has that price moved month over month,
and how often is stuff in stock. It used to be assembled by hand in a spreadsheet
from several separate exports. You've been asked to make it a single query so it can
be regenerated on demand instead of drifting out of date between quarters.

This pulls together everything from this module: joining across the category tree
(which isn't flat — it's a 4-level parent/child hierarchy), converting every price to
USD using a currency-and-date-specific exchange rate (no shortcuts — a snapshot's
currency and date determine which rate applies, and rates aren't guaranteed to exist
for every exact date, so you need an as-of lookup, not an exact-date join), rolling
everything up to the 8 top-level categories, computing a real percentile (not an
average — CEOs get misled by averages when there are outliers), and comparing each
month to the previous one with a window function.

Because this is a multi-evening build, work it in three checkpoints, each with its
own self-check you can run in `psql` before moving on. Only the final query in
`src/query.sql` is graded by the validator — the checkpoints are scaffolding to catch
mistakes early, not separate deliverables.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency,
  in_stock)` — 4,000,000 rows, 2025-01-01 through 2026-06-30 (18 full calendar
  months).
- `products(id, name, category_id, brand, first_seen_at)` — 200,000 rows.
- `categories(id, name, parent_id, level)` — 538 rows, 4 levels (0 = root through
  3 = leaf). There are exactly 8 root categories (`level = 0`, `parent_id IS NULL`).
  Every product's `category_id` may point to a category at any level, not just leaf
  categories — the rollup must walk up to the root regardless of what level the
  product's own category sits at.
- `exchange_rates(currency, rate_date, rate_to_usd)` — one row per currency per
  calendar day, `rate_to_usd` such that `price * rate_to_usd` = USD value. In this
  seed the coverage happens to be complete for every day in range, but do not rely on
  that — write the lookup as a genuine as-of join (latest rate on or before the
  snapshot's date) so it stays correct if a future reseed has gaps.

## What's required

One row per (calendar month, root category), 18 months x 8 roots, columns in this
exact order:

- `month` — first day of the calendar month (`date_trunc('month', captured_at)` cast
  to `date`).
- `root_name` — the name of the level-0 category this product's category rolls up to.
- `distinct_products` — count of distinct `product_id` values observed in that
  (month, root) bucket.
- `snapshot_count` — total `price_snapshots` rows in that bucket.
- `median_price_usd` — `percentile_cont(0.5)` of the as-of-USD-converted price across
  all snapshots in the bucket, rounded to 2 decimal places.
- `mom_median_change_pct` — percent change in `median_price_usd` versus the same root
  category's *previous* month in this result set:
  `(this_month - prev_month) / prev_month * 100`, rounded to 2 decimal places. `NULL`
  for each root category's first month (there is no previous month to compare
  against) and `NULL` if the previous month's median was exactly 0.
- `in_stock_share` — fraction of snapshots in the bucket with `in_stock = true`,
  rounded to 4 decimal places.

## Checkpoints

### CP1 — as-of converted monthly base

Build a CTE that, for every `price_snapshots` row, resolves its USD-converted price
using an as-of join against `exchange_rates` (latest `rate_date <= captured_at`'s
date, matching `currency`), and attaches the row's month bucket and product id.

Self-check in `psql`: `SELECT COUNT(*) FROM <cp1_cte>;` must equal the total row
count of `price_snapshots` (4,000,000) — if it's lower, your join is dropping rows
(likely an exchange rate or category lookup that doesn't match every row); if it's
higher, your as-of join is fanning out (likely matching more than one rate row per
snapshot).

### CP2 — rollup to root category + median

Add the category-tree walk: every product's `category_id` must resolve to one of the
8 root category names, regardless of which level it starts at. Group CP1's output by
(month, root) and compute `median_price_usd` via `percentile_cont`, plus
`distinct_products` and `snapshot_count`.

Self-check in `psql`: `SELECT COUNT(DISTINCT root_name) FROM <cp2_result>;` must equal
8. Also check `SELECT COUNT(*) FROM <cp2_result>;` — it should be at most 18 x 8 = 144,
and should equal 144 if every root category had at least one snapshot in every month
(true for this dataset).

### CP3 — month-over-month window + final shape

Add `in_stock_share` to the CP2 aggregation, then compute `mom_median_change_pct` with
a window function over `median_price_usd`, partitioned by `root_name`, ordered by
`month`.

Self-check in `psql`: for each root category, the row with the earliest `month` must
have `mom_median_change_pct IS NULL`, and every other row for that root must have it
`NOT NULL` (given the dataset has no zero medians and no missing months per root).

## Completion criteria

Write your final query into `src/query.sql`. From the module root:

```
uv run python validate.py 10
```

Must print `PASSED`.

## Estimated evenings

2-3

## Topics to read up on

- Recursive CTEs (`WITH RECURSIVE`) for walking a parent/child tree to its root
- As-of joins: `LATERAL` joins combined with `ORDER BY ... LIMIT 1`, versus
  `DISTINCT ON`, for "latest value on or before a given date"
- `PERCENTILE_CONT` vs `AVG` — why medians resist outliers that averages don't
- Window function frames: `PARTITION BY` + `ORDER BY` for `LAG()`-based
  period-over-period comparisons
- Multi-CTE query structuring: building a report as a pipeline of named,
  independently-checkable stages instead of one monolithic query
