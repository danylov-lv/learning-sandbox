# Hint 2

A B-tree index can only be searched efficiently starting from its leftmost
column. An index on `(product_id, order_id)` is genuinely useful for
`WHERE product_id = ...`, and even for `WHERE product_id = ... AND order_id
= ...` — but it cannot narrow down rows by `order_id` alone, because
`order_id` isn't the first thing the index is sorted by. Postgres would have
to scan (nearly) the whole index to find matches, which is worse than just
reading the table.

`q03.sql` filters on `order_id` alone. The existing composite index is
sorted by the wrong column first for that access pattern.
