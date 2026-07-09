# Hint 3

You want a composite `CREATE INDEX` on `orders` with `user_id` as the
leading column (it's the equality predicate — leftmost-prefix rule) and
`created_at` as the second column. Since the query asks for `created_at
DESC`, consider whether the index's second column should be declared
`DESC` too, so the index's on-disk order already matches what `ORDER BY
... DESC LIMIT 20` wants — letting the planner walk the index front-to-back
and stop after 20 rows instead of sorting.

Verify with `EXPLAIN (ANALYZE, BUFFERS)` afterwards: you're looking for a
single `Index Scan` (or `Index Only Scan`) node feeding straight into
`Limit`, with no `Sort` node in between.
