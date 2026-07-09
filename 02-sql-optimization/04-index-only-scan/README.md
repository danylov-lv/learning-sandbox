# 04 — Index-Only Scan

## Backstory

Two fires down, one to go this week. The mobile team is back — "My orders"
this time, the slim list view: date, status, total, twenty-five rows,
nothing else. It's the single hottest endpoint in the app by request
volume, and the SLA is the tightest yet: p95 under 30ms. The ticket
literally says "ideally served from the index alone" — someone on the
mobile team has clearly read about this before and is daring you to
deliver it.

That phrase is the point of this task. An index that already narrows
`orders` down to one user's rows in date order (which you may well have
built already) still has to jump to the heap to fetch `status` and
`total_amount` for every row it returns — unless the index itself carries
those columns. Whether Postgres can skip the heap entirely shows up as a
specific node type in the plan, and it doesn't always mean what you'd
expect on this particular table.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q04.sql` — the canonical, screaming query. **Do not modify this
  file.** Your fix must make this exact query fast.
- `tools/plan_check.py` — plan-assertion library used by the checker.
- `tools/baseline.py` — machine-local timing baseline.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `orders` has 6.0M
  rows, `users` has 1.0M.
- Whatever indexes you built in tasks 01/02, if working on the same
  database.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Record the baseline for `q04` once, from the module root:
   ```
   uv run python tools/baseline.py record queries/q04.sql
   ```
2. Run `EXPLAIN (ANALYZE, BUFFERS)` on `q04.sql`. Note the node type
   touching `orders` — is it `Index Scan` or `Index Only Scan`? These are
   not the same node, and the difference is exactly what this task is
   about.
3. Design (or extend) an index so that every column `q04.sql` selects is
   available directly from the index, without a trip to the heap for each
   matching row.
4. Look closely at the resulting plan's `Heap Fetches` count. If you get
   an `Index Only Scan` node but `Heap Fetches` is still high — close to
   the number of rows returned — that is not a failed fix. It's a real
   phenomenon on this particular table, and it's worth understanding *why*
   before you decide there's nothing more to do here. (Hint: think about
   what Postgres needs to know about a page's rows before it can trust the
   index alone, and what would have to run for it to know that. Running it
   yourself is your call, on your own copy of the database — it is not
   part of what the checker here verifies.)
5. Apply your fix against the live database yourself.
6. You may touch only `orders` and `users`. Do not modify `products`,
   `order_items`, `reviews`, `payments`, `inventory_events`, `sellers`, or
   `categories` in any way.

## Completion criteria

Run, from the module root:

```
uv run python 04-index-only-scan/tests/check.py
```

The checker verifies, in order:

1. `EXPLAIN` for `queries/q04.sql` shows an `Index Only Scan` on `orders`
   (not just any index scan).
2. The query runs meaningfully faster than your recorded baseline.
3. It also *reports* the plan's `Heap Fetches` count for `orders`, purely
   as information — this is not a pass/fail assertion. Read it.

All required checks must print `PASS`, and the final line must read
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- Covering indexes and the `INCLUDE` clause
- `Index Scan` vs. `Index Only Scan`: what has to be true for Postgres to
  trust an index without touching the table
- The visibility map and what it tracks per heap page
- `autovacuum` and what happens to the visibility map when it never runs

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes. It's there for
whoever maintains this module later, not for you mid-task — reading it now
would spoil the diagnostic work. Come back to it after you're done here if
you're curious.
