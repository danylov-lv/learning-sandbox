# 01 — Read the Plan

## Backstory

Kupitron is yours now — inherited along with whatever the previous team left
behind. First fire: the account page. Every logged-in user's "My Orders"
tab lists their 20 most recent orders, and it is the single slowest page in
the app. The mobile team has been getting App Store reviews mentioning the
spinner by name. Support has escalated it twice this week.

The query behind it (`queries/q01.sql`) looks harmless: one user, twenty
rows, sorted by date. On a table with a handful of orders per user this
would be instant. `orders` has 6 million rows. Something in how Postgres is
finding those 20 rows is very wrong, and your job is to find out what and
fix it — using nothing but `EXPLAIN` and your own reasoning.

This is the first task in the module because reading a plan is the one
skill everything else here depends on. Do not skip the diagnostic steps
below even if you already suspect the answer.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q01.sql` — the canonical, screaming query. **Do not modify this
  file.** Your fix must make this exact query fast.
- `tools/plan_check.py` — plan-assertion library used by the checker; also
  runnable as a CLI if you want to poke at plans yourself.
- `tools/baseline.py` — machine-local timing baseline.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `orders` has 6.0M
  rows, `users` has 1.0M.
- `src/fix.sql` — empty stub. You write your fix here.

## How to read an `EXPLAIN (ANALYZE, BUFFERS)` plan

You'll use this method on every task in this module, so it's worth doing
once, carefully.

1. **Get the plan.** From `psql` (or any client), run:
   ```sql
   EXPLAIN (ANALYZE, BUFFERS) <the query>;
   ```
   `ANALYZE` actually executes the query and reports what really happened,
   not just what the planner guessed. `BUFFERS` shows how many pages were
   touched.

2. **Read it as a tree, bottom-up.** Postgres prints the plan top-down, but
   execution happens bottom-up: the innermost (most indented) nodes run
   first and feed rows up to their parents. A `Limit` at the top just cuts
   off however many rows its child produced.

3. **For each node, ask three questions:**
   - *What kind of node is this?* `Seq Scan` reads every row of a table.
     `Index Scan` walks a B-tree and fetches matching rows from the table.
     `Sort` buffers all its input and reorders it — expensive if the input
     is large. `Limit` stops early, but only if its child can *stop* early
     too (a `Sort` generally cannot; an `Index Scan` that already returns
     rows in the right order can).
   - *How many rows did the planner expect, and how many did it actually
     get?* Every node reports both. A wildly-off estimate is a clue that
     something upstream (statistics, a bad predicate) is misleading the
     planner — file that away, but don't chase it yet on this task.
   - *How much work did it actually do?* `Buffers: shared hit=... read=...`
     tells you how many 8KB pages were touched. A node that touches
     millions of pages to return twenty rows is your prime suspect.

4. **Find the expensive node**, and ask: what access path *could* serve
   this node's job — the predicate in the `WHERE` clause and the columns in
   `ORDER BY` — without touching millions of rows? What would have to exist
   for Postgres to jump straight to the ~20 rows this user actually has,
   already in the right order?

Run this method on `queries/q01.sql` before reading any further. Note the
node type touching `orders`, its estimated vs. actual row counts, and its
buffer count.

## What's required

1. Record the baseline for `q01` once, from the module root:
   ```
   uv run python tools/baseline.py record queries/q01.sql
   ```
2. Diagnose the plan using the method above.
3. Write the DDL that fixes it into `01-read-the-plan/src/fix.sql`.
4. Apply your fix against the live database (e.g. `psql` or a short
   `psycopg` script that runs `src/fix.sql`).
5. You may touch only `orders` and `users`. Do not modify `products`,
   `order_items`, `reviews`, `payments`, `inventory_events`, `sellers`, or
   `categories` in any way.

## Completion criteria

Run, from the module root:

```
uv run python 01-read-the-plan/tests/check.py
```

The checker verifies, in order:

1. `EXPLAIN` for `queries/q01.sql` contains no `Seq Scan` on `orders`.
2. `orders` is reached through an index scan.
3. The query runs meaningfully faster than your recorded baseline.

All must print `PASS`, and the final line must read `PASSED`.

## Estimated evenings

1

## Topics to read up on

- B-tree index structure and the leftmost-prefix rule
- Composite index column order
- How a B-tree index scan can satisfy `ORDER BY` without a separate `Sort`
  node, and what index column order that requires
- `EXPLAIN (ANALYZE, BUFFERS)` output: node types, estimated vs. actual
  rows, buffer counts
