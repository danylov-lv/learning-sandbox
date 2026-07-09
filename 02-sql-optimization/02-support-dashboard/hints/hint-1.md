# Hint 1

Run `EXPLAIN (ANALYZE, BUFFERS)` on `queries/q02.sql` as it stands. What
node touches `orders`, and does it look like the problem from task 01, or
something else?

If you already built an index for task 01, check `\d orders` for it before
assuming you need to build anything new.
