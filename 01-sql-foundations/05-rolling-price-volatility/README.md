# 05 — Rolling Price Volatility

## Backstory

Product pages are getting a "price stability" badge, driven by a volatility
score computed from recent price history per (product, source). A colleague
already shipped a first cut using `ROWS N PRECEDING` — it looked fine in a
demo with clean daily snapshots, but once it hit real scraper cadence
(snapshots land irregularly, sometimes several times in one day, then nothing
for three days) the badge started flip-flopping in ways that don't match
reality: a pair with dozens of same-day re-scrapes gets an artificially
narrow, stale-looking rolling window, while a pair with sparse snapshots gets
a rolling window that stretches back months. You've been asked to redo the
scoring so the "recent" window means a fixed *calendar* span, not a fixed
*row count*.

## What's given

- The same `price_snapshots` table as the rest of the module.
- A fixed scope of 10 `(product_id, source_id)` pairs to compute over (these
  are genuinely high-traffic pairs in the seed — each has 500+ snapshots
  across the full 2025-01-01 .. 2026-06-30 window):

  | product_id | source_id |
  |-----------:|----------:|
  |     140857 |       186 |
  |     157376 |       186 |
  |     157376 |        91 |
  |     157376 |       113 |
  |     140857 |        91 |
  |      72050 |       113 |
  |     140857 |       113 |
  |      17943 |       113 |
  |      22654 |       186 |
  |      17943 |        91 |

- A stub at `src/query.sql`.

## What's required

Restrict to the 10 pairs above. For every snapshot of each pair, compute a
rolling average and rolling sample standard deviation of `price` using a
**30-day RANGE frame**: all snapshots of that same pair with `captured_at` in
`(current_row.captured_at - 30 days, current_row.captured_at]`, ordered by
`captured_at`.

This must use a `RANGE` frame (calendar-based), not a `ROWS` frame
(count-based) — on this data's irregular cadence they produce materially
different rolling windows, and only the `RANGE` semantics is graded. Say why
in your own words in `NOTES.md` once you've compared the two on one pair.

Then collapse each pair's per-snapshot rolling values down to one summary
row. Output columns, in this exact order:

- `product_id`
- `source_id`
- `snapshot_count` — total number of snapshots for that pair (all rows, not
  just ones with a full 30-day history)
- `avg_rolling_stddev` — average of the per-snapshot rolling stddev values,
  rounded to 4 decimal places (a snapshot whose rolling stddev is undefined
  because it has no other snapshots within the preceding 30 days should not
  count toward the average — aggregate functions skip nulls automatically,
  so this happens for free if you don't work around it)
- `max_rolling_stddev` — maximum of the per-snapshot rolling stddev values,
  rounded to 4 decimal places

One row per pair — 10 rows total.

## Completion criteria

Run `uv run python validate.py 05` from the module root. It must print
`PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- Window frame clauses: `ROWS` vs `RANGE` vs `GROUPS`
- Frame bounds: `PRECEDING` / `CURRENT ROW` / `FOLLOWING`, and using an
  `INTERVAL` as a `RANGE` bound
- `STDDEV_SAMP` vs `STDDEV_POP`
- Why `RANGE` requires a single, orderable `ORDER BY` column
- Two-stage aggregation: aggregating over a window-function result
