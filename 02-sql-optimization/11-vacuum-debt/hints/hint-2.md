# Hint 2

A dead tuple isn't just "wasted space" in the abstract — it's a row
version that's no longer visible to any transaction but that Postgres
hasn't reclaimed yet. Until something vacuums the page it lives on, that
page can't be marked all-visible in the visibility map. And the visibility
map is exactly what `Index Only Scan` checks before it decides whether it
can trust the index alone or has to go touch the heap anyway (that's
`Heap Fetches` in an `EXPLAIN ANALYZE` — not a bug, a direct consequence of
an unvacuumed page).

So: dead tuples accumulate -> visibility map stays empty -> `Index Only
Scan` degrades into "index scan that also fetches every row from the
heap," silently, with no error and no warning, just an `EXPLAIN` node
whose name doesn't match what it's actually doing.

Now think about the two ways to reclaim space: plain `VACUUM` marks dead
tuples' space as reusable *by future inserts into the same table*, without
shrinking the file on disk or taking a lock that blocks reads/writes.
`VACUUM FULL` rewrites the entire table into a new, compact file and
returns space to the OS — but it takes an `ACCESS EXCLUSIVE` lock for the
duration, blocking everything, reads included, on that table. For a table
still taking live traffic, is that a lock you can afford, or would a
concurrent-friendly extension (there's a well-known one that does what
`VACUUM FULL` does without the exclusive lock, at the cost of needing
extra disk space and a new index rebuild) be worth knowing about instead?
Not every one of the three tables here necessarily needs the same answer.
