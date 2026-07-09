Structure it in two stages:

1. A CTE that selects `product_id, source_id, captured_at, price` plus a
   `prev_price` column computed with `LAG(...) OVER (PARTITION BY
   product_id, source_id ORDER BY captured_at)`.
2. An outer query over that CTE that:
   - discards rows where `prev_price IS NULL` (the first snapshot of a pair
     has nothing to compare against),
   - discards rows where `price >= prev_price` (not a drop),
   - computes `drop_pct = (prev_price - price) / prev_price * 100`,
   - keeps only rows where `drop_pct > 70`,
   - rounds `drop_pct` to 2 decimal places in the final `SELECT`.

Watch the sign and the divisor in the percentage formula — it should be
positive for a drop, and normalized against `prev_price`, not `price`.
