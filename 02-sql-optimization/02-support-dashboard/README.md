# 02 — Support Dashboard

## Backstory

With the account page fixed, the next fire comes from support. Every time
an agent opens a ticket, the dashboard shows a per-customer summary panel:
how many orders the customer placed in the last 90 days, how much they
spent, and when their last order was. Support leads say agents are waiting
ten-plus seconds per ticket just for this panel to load, and it's dragging
down every metric the team is measured on.

The query (`queries/q02.sql`) is a different shape than `q01`: it's an
aggregate over a *range* (`created_at >= now() - interval '90 days'`), not
a `LIMIT`-ed lookup of the most recent rows. Same table, same `user_id`
filter, different job.

If you already fixed `q01` in the previous task, look hard at what you
built before reaching for `CREATE INDEX` again. An index designed with only
one query shape in mind is a wasted opportunity — and a redundant index is
its own kind of defect (extra write overhead, extra pages to keep warm in
cache, extra size, for zero benefit). Figure out whether your existing
index already serves this predicate before deciding you need a new one.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q02.sql` — the canonical, screaming query. **Do not modify this
  file.** Your fix must make this exact query fast.
- `tools/plan_check.py` — plan-assertion library used by the checker.
- `tools/baseline.py` — machine-local timing baseline.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `orders` has 6.0M
  rows, `users` has 1.0M.
- Whatever state `orders` is in after task 01, if you did it on this same
  database. If you're starting fresh, `orders` has only its original
  `(status)` index.
- `src/fix.sql` — empty stub. You write your fix here (which may legitimately
  be empty, with a comment explaining why).

## What's required

1. Record the baseline for `q02` once, from the module root:
   ```
   uv run python tools/baseline.py record queries/q02.sql
   ```
2. Run `EXPLAIN (ANALYZE, BUFFERS)` on `q02.sql` and diagnose it the same
   way you did in task 01.
3. Decide: does an index you already have cover this query's access
   pattern (leftmost-prefix rule again — think about what `user_id =` plus
   a `created_at` range needs from a composite index, and whether column
   order matters the same way here as it did for the `ORDER BY` in `q01`)?
   If yes, your `src/fix.sql` can say so and add no new DDL. If no, design
   the index (or adjust the existing one) and write it there.
4. Apply whatever DDL you decide on against the live database yourself.
5. You may touch only `orders` and `users`. Do not modify `products`,
   `order_items`, `reviews`, `payments`, `inventory_events`, `sellers`, or
   `categories` in any way.

## Completion criteria

Run, from the module root:

```
uv run python 02-support-dashboard/tests/check.py
```

The checker verifies, in order:

1. `EXPLAIN` for `queries/q02.sql` contains no `Seq Scan` on `orders`.
2. `orders` is reached through an index scan.
3. The query runs meaningfully faster than your recorded baseline.

This passes whether you added new DDL in this task or not — what matters
is the resulting plan and timing, not how many `CREATE INDEX` statements
you ran. All three checks must print `PASS`, and the final line must read
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- Composite index range scans vs. equality scans on the leading column
- The leftmost-prefix rule applied to a mix of equality and range
  predicates
- Index bloat and write-amplification cost of redundant indexes
- `Bitmap Heap Scan` / `Bitmap Index Scan` — when the planner picks these
  over a plain `Index Scan`
