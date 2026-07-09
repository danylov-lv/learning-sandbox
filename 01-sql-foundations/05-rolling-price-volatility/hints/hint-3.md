Two stages, similar shape to a running-total-then-summarize pattern:

1. Filter `price_snapshots` down to the 10 given `(product_id, source_id)`
   pairs (a `VALUES` list joined against the table, or an `IN` on the pair,
   works fine).
2. In a CTE, for every remaining row compute:
   - `rolling_stddev` = `STDDEV_SAMP(price)` windowed by `PARTITION BY
     product_id, source_id ORDER BY captured_at RANGE BETWEEN INTERVAL '30
     days' PRECEDING AND CURRENT ROW`
   - (you don't need to keep the rolling average in the final output, but
     computing it the same way is a good sanity check while developing)
3. In an outer query, `GROUP BY product_id, source_id` over that CTE and
   compute `COUNT(*)`, `AVG(rolling_stddev)`, `MAX(rolling_stddev)`, rounding
   the last two to 4 decimals.

To see the ROWS-vs-RANGE difference yourself before you commit to RANGE, try
computing both frames for just one pair and diff the per-row stddev values —
the disagreement should be obvious wherever snapshots cluster or gap.
