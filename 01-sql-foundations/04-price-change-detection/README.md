# 04 — Price Change Detection

## Backstory

The alerting service you maintain pings the marketing channel whenever a tracked
product's price drops sharply at a source — the idea is to catch flash sales and
competitor undercuts fast. Marketing has started to complain that some "drops"
are actually repricing glitches: a scraper hiccup records a garbage price for
one snapshot, or a source briefly lists a bundle/refurb SKU under the same
product_id. Before the alert fires anything else, you've been asked to produce
the raw list of qualifying drops so the on-call analyst can eyeball them before
the threshold and destination channel get finalized.

You already know `LAG()`/`LEAD()` from building cursors over Kafka-consumed
events — this is the same idea, just partitioned over price history in SQL
instead of a stream.

## What's given

- Read-only access to `price_snapshots(id, product_id, source_id, captured_at,
  price, currency, in_stock)` in the seeded sandbox Postgres (see module
  README for connection details).
- Snapshot cadence per (product_id, source_id) pair is irregular — anywhere
  from a handful of snapshots to several hundred across the 2025-01-01 ..
  2026-06-30 window, with gaps of hours to several days.
- A stub at `src/query.sql`.

## What's required

For each `(product_id, source_id)` pair, order snapshots by `captured_at` and
compare each snapshot's price to the immediately preceding snapshot for the
same pair (i.e. the previous row in that ordering — not a fixed time window).
Keep only consecutive-snapshot drops where the price fell by **more than 70%**
relative to the previous snapshot.

Output one row per qualifying drop, columns in this exact order:

- `product_id`
- `source_id`
- `captured_at` — the timestamp of the *lower* (post-drop) snapshot
- `prev_price` — the price of the preceding snapshot for that pair
- `price` — the price at `captured_at`
- `drop_pct` — `(prev_price - price) / prev_price * 100`, rounded to 2 decimal
  places

There is no top-N cutoff here — the 70% threshold alone determines the row
set for this seed, and it lands in the low dozens, small enough to eyeball.
No further tie-breaking is needed since every qualifying (pair, captured_at)
combination is already unique.

## Completion criteria

Run `uv run python validate.py 04` from the module root. It must print
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- Window functions: `LAG` / `LEAD`
- `PARTITION BY` vs `GROUP BY`
- Window function `ORDER BY` and how it differs from the query's final
  `ORDER BY`
- Filtering on a window function result (why it can't go directly in `WHERE`)
