# 08 — Index Audit: Reviews

## Backstory

Nothing about `reviews` is screaming right now — that's exactly why nobody
has looked at it. But while you were chasing the order-detail and
storefront fires, you noticed something in passing: `reviews` writes are
slower than they have any right to be for a 3.0M-row table with no
`UPDATE`s or `DELETE`s. Every `INSERT` has to maintain five indexes. You
pull up `\d reviews` and start counting: a plain index on `product_id`, two
composites that both *also* start with `product_id`, and one index on
`review_text` — the full review body — that is enormous.

Nobody can tell you offhand why all four exist. Before you touch anything,
you go find out what actually reads this table. `src/workload.md` is what
you found: the complete, current list of read patterns against `reviews`,
gathered from the query log. Nothing else touches it.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `src/workload.md` — the documented read workload against `reviews`. This
  is ground truth: assume it is complete and accurate. Any index you cannot
  justify against it (or against the stated write rate) is a candidate for
  removal.
- `tools/plan_check.py`, `tools/baseline.py`.
- The live Postgres instance; `reviews` has 3.0M rows.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Read `src/workload.md` and cross-reference it against the five indexes
   currently on `reviews` (`\d reviews` or `pg_indexes`).
2. For each index, decide: does at least one documented read pattern
   actually need it, or is it redundant / dead weight relative to another
   index that already covers the same leading column(s)?
3. Write the `DROP INDEX` statements you can justify into
   `08-index-audit-reviews/src/fix.sql`, and apply them against the live
   database yourself.
4. Only `order_items`, `products`, `reviews` (and read-only FK joins) may be
   touched. Leave `orders`, `users`, `payments`, `inventory_events`,
   `sellers`, `categories` untouched.
5. Do not drop an index that a documented read pattern needs. The checker
   re-runs the workload from `src/workload.md` and will fail you if any of
   it falls back to a sequential scan.

## Completion criteria

Run, from the module root:

```
uv run python 08-index-audit-reviews/tests/check.py
```

The checker verifies:

1. The indexes you targeted are actually gone (checked against
   `pg_indexes`, not against your `fix.sql` text).
2. Every read pattern in `src/workload.md`, re-run against the live table,
   still avoids a `Seq Scan` on `reviews` and is served by an index.
3. It reports (informationally — no pass/fail threshold) how much faster a
   batch insert into `reviews` runs with fewer indexes to maintain, so you
   can see the write-amplification win you were chasing.

## Estimated evenings

1-2

## Topics to read up on

- Index write amplification: what every index actually costs on `INSERT`
- Redundant indexes: when one composite index makes a single-column index
  on its leading column pointless
- How to tell an index is unused in practice (`pg_stat_user_indexes`, and
  why you should be suspicious of a huge index on a rarely-filtered text
  column)
- The tradeoff between read latency and write throughput when deciding
  which indexes earn their keep
