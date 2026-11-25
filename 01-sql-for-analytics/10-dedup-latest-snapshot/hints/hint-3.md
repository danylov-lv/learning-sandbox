# Hint 3

Shape of the query, without the actual SQL:

1. CTE `latest`: from `price_snapshots` joined to `sources` (to bring in `tier`),
   deduplicate down to one row per `(product_id, source_id)` using the tie-breaker
   from the README — keep `price`, `currency`, `in_stock`, and `tier` for each
   surviving row.
2. Final `SELECT`: from `latest`, `GROUP BY tier, currency`, computing:
   - `COUNT(*)` for `pair_count`
   - `ROUND(AVG(price), 2)` for `avg_latest_price`
   - a rounded average of a 0/1 indicator derived from `in_stock` for
     `in_stock_share` — turning a boolean into a number you can average is the part
     worth thinking about (a `CASE` expression, or a cast, both work).

Before trusting the aggregation, sanity-check step 1 alone: run it standalone and
confirm the row count equals the number of distinct `(product_id, source_id)` pairs
in `price_snapshots` — no more, no less.
