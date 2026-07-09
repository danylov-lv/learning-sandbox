# Hint 3

Shape of the query, without the actual SQL:

1. `WITH RECURSIVE root_category AS (...)` — maps every category id to
   `(root_id, root_name)`, as described in hint 2.
2. `base AS (...)` — from `price_snapshots`, join `products` (for `category_id`),
   join `root_category` (via `products.category_id`), and a `LATERAL` join against
   `exchange_rates` for the as-of rate. Select: month bucket, `root_name`,
   `product_id`, `in_stock`, and `price * rate_to_usd AS price_usd`.
   Self-check this against CP1 before moving on.
3. `monthly AS (...)` — `GROUP BY month, root_name` over `base`, computing
   `COUNT(*)`, `COUNT(DISTINCT product_id)`, `PERCENTILE_CONT(0.5) WITHIN GROUP
   (ORDER BY price_usd)` rounded, and the in-stock share. Self-check against CP2.
4. Final `SELECT` from `monthly`, adding the `LAG()`-based month-over-month
   percentage as a window expression, with a `CASE`/`NULLIF` guard for the first
   month and for a zero previous median. Self-check against CP3.
5. No final `LIMIT` — the graded output is all 144 rows.

Work each CTE as its own standalone query in `psql` first (temporarily replacing
later CTEs with a plain `SELECT * FROM <stage> LIMIT 20`), confirm the self-check
counts from the README, then assemble the full pipeline.
