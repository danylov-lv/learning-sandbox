# Hint 3

If the plan already shows an `Index Scan` or `Bitmap Heap Scan` on
`orders` with no `Seq Scan` in sight, and timing already beats the
baseline by a wide margin, you're done — write that reasoning into
`src/fix.sql` as a comment and move on. There is no bonus for adding DDL
the planner doesn't need.

If it's still seq-scanning, the fix is the same shape as task 01: a
composite index with `user_id` leading. What differs from task 01 is that
this query doesn't need index-order to match an `ORDER BY`, since it's
aggregating with `count()`/`sum()`/`max()`, not returning ordered rows.
