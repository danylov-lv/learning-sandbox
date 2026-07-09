# Hint 1

`\d order_items` shows an index that mentions `order_id`. Before assuming
that index is usable for `WHERE oi.order_id = 4242`, check exactly which
column it starts with, not just which columns it contains.

Run `EXPLAIN (ANALYZE, BUFFERS)` on `queries/q03.sql` as it stands today and
look at which node is doing the expensive work. Is it hitting an index at
all for `order_items`?
