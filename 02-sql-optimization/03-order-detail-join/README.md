# 03 — Order Detail Join

## Backstory

Packing slips are backing up in the warehouse. Every time a picker scans an
order, the app renders the order detail page — line items, quantities, and
product titles — and that page is now the slowest thing in the building.
Ops has started calling it "the spinner." The query behind it
(`queries/q03.sql`) is trivial: one order, its line items, joined to
`products` for the title. It should be instant. It is not.

You pull up `EXPLAIN` on the query and something looks off. There *is* an
index on `order_items` that includes `order_id` — you can see it right there
in `\d order_items`. So why is Postgres seq-scanning a 13.8M-row table for a
single order?

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q03.sql` — the canonical, screaming query. **Do not modify this
  file.** Your fix must make this exact query fast.
- `tools/plan_check.py` — plan-assertion library used by the checker.
- `tools/baseline.py` — machine-local timing baseline.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass: `sandbox`),
  container `02-sql-optimization-postgres-1`. `order_items` has 13.8M rows,
  `products` has 2.0M.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Record the baseline for `q03` once, from the module root:

   ```
   uv run python tools/baseline.py record queries/q03.sql
   ```

2. Figure out why the existing index on `order_items` does not help this
   query, even though it *contains* `order_id`.
3. Write the DDL that fixes it into `03-order-detail-join/src/fix.sql`.
4. Apply your fix against the live database (e.g. `psql` or a short
   `psycopg` script that runs `src/fix.sql`).
5. You may touch only `order_items`, `products`, `reviews`, and read-only
   joins to their foreign-key targets. Do not modify `orders`, `users`,
   `payments`, `inventory_events`, `sellers`, or `categories` in any way.

## Completion criteria

Run, from the module root:

```
uv run python 03-order-detail-join/tests/check.py
```

The checker verifies, in order:

1. `EXPLAIN` for `queries/q03.sql` contains no `Seq Scan` on `order_items`.
2. The plan reaches `order_items` through an index whose *leading* column
   is `order_id` (checked against `pg_indexes`, not just guessed from the
   plan — having `order_id` somewhere in an index is not the same as having
   it first).
3. The query runs meaningfully faster than your recorded baseline.

All three must print `PASS`, and the final line must read `PASSED`.

## Estimated evenings

1

## Topics to read up on

- B-tree index column order and the leftmost-prefix rule
- How Postgres chooses between Seq Scan, Index Scan, and Nested Loop
- `EXPLAIN (ANALYZE, BUFFERS)` output: estimated vs. actual rows
- Composite indexes vs. multiple single-column indexes
