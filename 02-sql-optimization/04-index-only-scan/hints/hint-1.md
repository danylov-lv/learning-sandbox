# Hint 1

Run `EXPLAIN (ANALYZE, BUFFERS)` on `queries/q04.sql`. If you already have
an index from task 01/02 that leads with `user_id, created_at`, you'll
likely see a plain `Index Scan`, not `Index Only Scan` — even though the
index already avoids a `Seq Scan` and a `Sort`. Why would Postgres still
need to visit the heap here, given what columns this query actually
selects?
