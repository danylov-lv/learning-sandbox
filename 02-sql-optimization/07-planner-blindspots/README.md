# 07 — Planner Blindspots

## Backstory

The account page, the support dashboard, and the mobile order list are all
fast now. Ops is next in line, and this one is stranger than the others:
the query isn't scanning the whole table, isn't missing an index, and yet
it's slow — and getting slower as the data grows, not staying flat the way
a correctly-indexed query should.

Every morning, warehouse ops pulls a queue of orders stuck in `processing`
from the last 30 days, joined with customer contact info for follow-up
calls (`src/given_query.sql`). You didn't write this query and you
shouldn't rewrite it — it's a reasonable, ordinary query. Your job is to
figure out why Postgres is choosing a bad *plan* for it, something no
amount of adding indexes will fix on its own, because the problem isn't
missing access paths. It's what the planner *believes* about the data.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB). Read the comments on `orders` closely —
  every defect on this table is documented there.
- `src/given_query.sql` — the query this task is about. **Do not modify
  this file.** It is provided, not written by you.
- `tools/plan_check.py` — plan-assertion library used by the checker,
  including `rows_estimate_error`, which reports the worst estimated-vs-
  actual row mismatch anywhere in a plan.
- `tools/baseline.py` — machine-local timing baseline (not required for
  this task's checker, but useful for your own before/after comparison).
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `orders` has 6.0M
  rows, `users` has 1.0M.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Run `EXPLAIN (ANALYZE, BUFFERS)` on `src/given_query.sql`. Compare the
   estimated row count at each node against the actual row count. Find the
   node where these two numbers are wildly apart — not off by a little,
   off by orders of magnitude.
2. Once you've found it, ask *why* the planner would believe that. What
   does Postgres use to estimate how many rows a `status = 'processing'`
   filter will match? Where does that information come from, and how
   current is it, given what `seed/schema.sql`'s comments say about
   `autovacuum` on this table?
3. Look at `orders.status`'s statistics target (`\d+ orders` or query
   `pg_attribute`/`pg_stats` directly) and think about whether — given how
   few distinct values `status` actually has — the target size is really
   the limiting factor, or whether the bigger problem is simply that the
   planner has never looked at the data in its current shape.
4. Write your fix into `07-planner-blindspots/src/fix.sql` and apply it
   against the live database yourself.
5. You may touch only `orders` and `users`. Do not modify `products`,
   `order_items`, `reviews`, `payments`, `inventory_events`, `sellers`, or
   `categories` in any way.

## Completion criteria

Run, from the module root:

```
uv run python 07-planner-blindspots/tests/check.py
```

The checker verifies:

1. The worst row-estimate error anywhere in the plan for
   `src/given_query.sql` drops below a calibrated threshold (today it's
   off by four orders of magnitude; after a correct fix it should be
   nowhere close).
2. A structural signature of a plan built on trustworthy estimates: the
   planner adds a `Memoize` node around the inner side of the join, which
   it only does when it has a sane idea of how many times that side will
   actually be probed.

Both checks must print `PASS`, and the final line must read `PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- How the query planner estimates selectivity from `pg_stats`
  (`n_distinct`, most-common values and their frequencies)
- `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`, and what a higher
  target buys you (and what it doesn't, when the real problem is
  something else)
- `ANALYZE` — what it recomputes, and why nothing in Postgres runs it for
  you automatically if `autovacuum` is disabled on a table
- `Memoize` nodes and when the planner introduces them
- Nested Loop vs. Hash Join: what estimated row counts have to do with
  which one the planner picks

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes. It's there for
whoever maintains this module later, not for you mid-task — reading it now
would spoil the diagnostic work. Come back to it after you're done here if
you're curious.
