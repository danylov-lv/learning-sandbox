# Hint 3

`orders.status` has only 7 distinct values, so `pg_stats.n_distinct` isn't
really your problem — a small `most_common_vals` list can already capture
all 7. The core issue is that whatever list is there was computed before
a large, differently-distributed batch of rows landed in the table, and
nothing has recomputed it since (no autovacuum, no manual `ANALYZE` since
then).

Your fix has two independent levers, and the task wants you to reason
about both: `ALTER TABLE orders ALTER COLUMN status SET STATISTICS <n>`
raises how many most-common-values/histogram buckets get sampled for that
column, and `ANALYZE orders` is what actually recomputes `pg_stats` from
the table's current contents, at whatever target is currently set. One of
these two is doing the real work here, given how few distinct values
`status` has — figure out which, and don't assume you need to change the
target enormously to see the plan flip.
