# Hint 3

`CREATE INDEX ... ON orders (user_id, created_at DESC) INCLUDE (status,
total_amount)` gets you an `Index Only Scan` node in the plan. But if you
check `Heap Fetches` on that node afterwards and it's not zero — possibly
equal to every row returned — that's not your index definition failing.

An `Index Only Scan` can only skip the heap for rows on a page the
visibility map marks all-visible, meaning: no transaction currently
running could see an older version of any row on that page. That bit gets
set by vacuum. Check `seed/schema.sql`'s comments on `orders` for what's
been done to autovacuum on this table, and check `pg_stat_user_tables` for
`orders` to see when (if ever) it was last vacuumed. That's your answer
for why `Heap Fetches` looks the way it does — and it's the same defect
you'll be looking at more directly in a later bloat/vacuum task.
