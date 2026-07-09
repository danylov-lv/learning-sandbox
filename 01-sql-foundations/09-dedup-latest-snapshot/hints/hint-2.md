# Hint 2

`DISTINCT ON (partition_columns)` keeps the first row per partition according to
whatever `ORDER BY` you give the query — the `ORDER BY` must start with the same
columns as the `DISTINCT ON` list, then continue with your tie-breaker columns. Get
the tie-breaker direction right: you want the most recent snapshot, and among equal
timestamps, the one with the highest id.

The `ROW_NUMBER()` alternative: partition by the same columns, order by the same
tie-breaker chain, then keep only the rows where the row number equals 1 (this needs
an outer query or CTE, since window function results can't be filtered directly in
the same `SELECT`'s `WHERE`).

Once you have one row per `(product_id, source_id)`, join to `sources` (if you
haven't already) to get `tier`, then it's a standard `GROUP BY tier, currency`.
