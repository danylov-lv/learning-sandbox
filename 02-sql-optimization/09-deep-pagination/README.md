# 09 — Deep Pagination

## Backstory

The admin UI has an "inventory event feed" — a paged table of every stock
movement, newest first, with Prev/Next buttons wired to plain `OFFSET` /
`LIMIT`. Nobody noticed a problem for months: most support agents look at
the first page or two. Then a support lead needed to page all the way back
to investigate a months-old ticket, and the request timed out. Shallow
pages still load instantly — `idx_inventory_events_occurred_at` covers
those fine. It's only the deep pages that fall over, and they get *slower*
the deeper you go.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB). `inventory_events` has an index on
  `occurred_at` alone and one on `product_id` alone.
- `src/given_query.sql` — the current deep-page query. **Do not modify this
  file.** It is the query the feed actually runs; your job is to reproduce
  its output for the same page, not to change it.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `inventory_events`
  has 9.0M rows spanning January 2025 through today.
- `tools/plan_check.py` and `tools/baseline.py` — the plan-assertion and
  timing-baseline helpers used by the checker.
- `src/page_query.sql` — stub. You write your keyset rewrite here.
- `src/fix.sql` — empty stub for an optional supporting index. You may not
  need it; see "What's required" below.

## What's required

1. Read `src/given_query.sql`. Run `EXPLAIN (ANALYZE, BUFFERS)` on it and
   look at what the executor actually does with `OFFSET 800000`: does it
   jump straight to row 800,001, or does it produce every row up to that
   point and throw most of them away? Note which plan node absorbs that
   cost.
2. Design a keyset ("cursor") rewrite in `src/page_query.sql`. The contract:
   your query is handed the `(occurred_at, id)` of the **last row of the
   previous page**, as psycopg named parameters `%(cursor_occurred_at)s`
   and `%(cursor_id)s`, and must return the next 100 rows in the same
   `occurred_at DESC, id DESC` order — with no `OFFSET` anywhere in the
   query.
3. `occurred_at` is not unique — many events land in the same second. A
   naive `WHERE occurred_at < %(cursor_occurred_at)s` will silently skip or
   duplicate rows whenever a page boundary falls inside a tied group. Your
   `WHERE` clause needs to encode "strictly before this (occurred_at, id)
   pair in the sort order," not just "before this timestamp."
4. Investigate whether the existing single-column index on `occurred_at`
   is enough to make your rewrite efficient, or whether the tie-break
   comparison forces a plan that still isn't good. If you decide you need
   a supporting index, write it into `src/fix.sql` and apply it against the
   live database yourself (this file is not run for you). It is entirely
   possible for the correct answer to be "no new index needed" — the
   checker does not require `src/fix.sql` to contain anything.
5. You may touch only `inventory_events`. Do not modify `products`, `orders`,
   `order_items`, `reviews`, `payments`, `users`, `sellers`, or `categories`
   in any way.

## Completion criteria

First record the timing baseline once, from the module root:

```
uv run python tools/baseline.py record 09-deep-pagination/src/given_query.sql --id given_query_09
```

Then run:

```
uv run python 09-deep-pagination/tests/check.py
```

The checker verifies:

1. Given the cursor of the row immediately before the deep page, your
   `src/page_query.sql` returns exactly the same 100 rows, in the same
   order, as `src/given_query.sql`'s `OFFSET 800000 LIMIT 100`.
2. Walking 3 consecutive pages by repeatedly applying the cursor from the
   last row received matches the corresponding 3 `OFFSET` pages
   row-for-row — this is what catches a tie-break bug that only shows up
   when a page boundary lands inside a group of same-second events.
3. Your keyset query is at least 30x faster than the `OFFSET` deep page,
   timed against the baseline you recorded above.
4. Your query's plan reaches `inventory_events` through an Index Scan-family
   node that only touches a small number of rows — proof the executor is
   seeking to the cursor, not walking and discarding 800,000 rows.

All four checks must print `PASS`, and the final line must read `PASSED`.

## Estimated evenings

1

## Topics to read up on

- How `OFFSET` / `LIMIT` is actually executed by Postgres (and by most
  relational engines)
- Keyset pagination ("seek method") vs. offset pagination
- Row-value comparison predicates (`WHERE (a, b) < (x, y)`) and how the
  planner can use them against a multi-column index
- Composite B-tree indexes and the leftmost-prefix rule
- Stable sort ordering and tie-breaking columns in `ORDER BY`

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes. It's off-limits
before you attempt this task — read it afterward if you're curious how it
was calibrated.
