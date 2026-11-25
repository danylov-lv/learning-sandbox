# Hint 3

Shape of the query, without the actual SQL:

1. CTE #1: for every `price_snapshots` row, compute two window `ROW_NUMBER()`s as
   described in hint 2 — one partitioned by `(product_id, source_id)` only, one
   partitioned by `(product_id, source_id, in_stock)` — both ordered by
   `captured_at`. Emit their difference as a `grp` column alongside `product_id`,
   `source_id`, `in_stock`, `captured_at`.
2. CTE #2: filter CTE #1 to `in_stock = false`, then `GROUP BY product_id, source_id,
   grp`, computing `COUNT(*)`, `MIN(captured_at)`, `MAX(captured_at)`.
3. Final `SELECT` from CTE #2: order by the tie-breaker chain from the README, then
   `LIMIT 25`.

Sanity check while developing: pick one `(product_id, source_id)` pair by hand, pull
its raw snapshots ordered by `captured_at`, and manually count the longest false-run.
Compare against what your query produces for that pair before trusting the top-25.
