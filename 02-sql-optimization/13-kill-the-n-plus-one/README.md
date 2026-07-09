# 13 — Kill the N+1

## Backstory

The internal support dashboard renders a customer's recent orders with
their line items (joined to product titles) and each order's latest
payment status. It was written the way an ORM encourages you to think:
fetch the orders, then loop over them fetching each one's items and
payment separately. For a lightly-active customer that's fine. For a
heavy user with dozens of orders, it's 1 + 2*N round trips to the
database for a single page load, p95 latency is terrible, and the
connection pool is saturated by agents who are all just trying to look up
one customer at a time.

## What's given

- `src/dashboard.py` — the STOCK naive implementation of
  `fetch_dashboard(conn, user_id, limit=30)`. This is the starting defect,
  not a solution: it runs one query for the user's orders, then, for
  *each* order, one query for its line items (joined to `products` for the
  title) and one query for its latest payment. Read it and confirm you
  understand exactly why it's 1 + 2*N queries before touching anything.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`). `orders` has 6.0M rows, `order_items` 13.8M, `products`
  2.0M, `payments` 5.7M.
- **A note on the stock schema**: `orders` has no index on `user_id` yet
  (that's task 01/02's territory) and `order_items` has no index leading
  with `order_id` (that's task 03's territory — defect (b) in
  `seed/schema.sql`). You are not required to add either index for this
  task; the point here is the *query count*, not raw milliseconds. If
  you've already done tasks 01-03 on this same database, the fixed version
  will additionally be fast in absolute terms; if you haven't, it'll still
  be dramatically fewer round trips, just against unindexed tables. The
  checker's timing output is informational only for exactly this reason —
  it does not gate on absolute milliseconds.

## What's required

Rewrite `fetch_dashboard()`'s data-access layer — same function signature,
same returned structure (documented in the docstring in `src/dashboard.py`)
— so that it issues a **constant number of queries regardless of how many
orders the user has**. Target: 3 queries total (one for orders, one
set-based query for items+products, one for payments), or up to 4 if your
approach benefits from splitting a step into two queries. A single
JSON-aggregating query that returns everything in one round trip is also a
valid approach if you'd rather do the reassembly in SQL instead of Python.

Whichever shape you pick, the returned Python structure must be identical
to what the stock version returns for the same inputs — same order-by,
same nesting, same string formatting for decimals.

## Completion criteria

Run, from the module root:

```
uv run python 13-kill-the-n-plus-one/tests/check.py
```

The checker calls `fetch_dashboard()` for three fixed user ids (each with
60 real orders) while counting every query your implementation issues,
and separately re-derives the same data with its own independent,
set-based SQL to check for exact result parity. It verifies:

1. **Result parity** — your function's output matches the independently
   computed reference exactly, for all three users.
2. **Query count** — every call issues at most 4 queries, independent of
   how many orders the user has (the naive version issues 61 for a
   30-order page).

Both checks must print `PASS`, and the final line must read `PASSED`.
Query timing is printed as `info` only — see the note above on why it
isn't a pass/fail gate here.

## Estimated evenings

1

## Topics to read up on

- The N+1 query problem and why ORMs are especially prone to it
- Set-based fetching with `= ANY(array)` / `IN (...)` over a batch of keys
  collected up front
- `DISTINCT ON` for "give me the latest row per group" in Postgres
- Reassembling a flat result set into nested application objects (grouping
  by a foreign key in application code) vs. doing the aggregation in SQL
  (`json_agg`, `jsonb_build_object`)
- Counting round trips: connection-level statement logging, or thinking in
  terms of `pg_stat_statements`-style call counts

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes, including the
measured query counts and timings behind this task's thresholds. It's
there for whoever maintains this module later, not for you mid-task —
reading it now would spoil the diagnostic work. Come back to it after
you're done here if you're curious.
