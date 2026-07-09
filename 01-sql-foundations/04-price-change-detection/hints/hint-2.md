`LAG(price) OVER (PARTITION BY product_id, source_id ORDER BY captured_at)`
gives you the previous snapshot's price on the same row as the current
snapshot's price. Once both prices are on one row, the drop percentage is
just arithmetic on the two columns.

Remember that a window function's result can't be referenced in the same
`SELECT`'s `WHERE` clause — you'll need to wrap the windowed expression in a
subquery or CTE before you can filter on it (or on the computed drop_pct).
