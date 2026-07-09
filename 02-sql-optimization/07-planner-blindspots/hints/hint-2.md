# Hint 2

The planner estimates `status = 'processing'` selectivity from
`pg_stats.most_common_vals`/`most_common_freqs` for `orders.status`. Query
`pg_stats` for that column and compare the frequencies it reports against
the frequencies you get from `SELECT status, count(*) FROM orders GROUP BY
status` — for the *whole* table, and then again restricted to just the
last 30-90 days. Do the numbers for "processing" match, for either
window?

`seed/schema.sql`'s comment on `orders` mentions `autovacuum_enabled =
off`. What does that imply for how often `ANALYZE` runs on this table, and
therefore how current `pg_stats` actually is relative to what got loaded
into `orders` most recently?
