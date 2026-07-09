# Hint 1

Start in the catalog, not with a `VACUUM` command. `pg_stat_user_tables`
has columns for exactly this situation: `n_live_tup`, `n_dead_tup`,
`last_vacuum`, `last_autovacuum`, `last_analyze`, `last_autoanalyze`. What
do the values look like for `orders`, `payments`, and `inventory_events`
compared to some other table in the schema that hasn't been touched?

Separately, `pg_class.reloptions` stores per-table storage parameters as a
text array. Query it for the three tables in question. What's in there,
and what does `seed/schema.sql`'s `ALTER TABLE ... SET (...)` block for
each of these tables tell you about how it got that way?

Why would `last_vacuum` being NULL matter beyond "nobody happened to run
it"? Think about what else in this module depends on a table having been
vacuumed at least once (there's a task elsewhere in this module whose
covering index technically works but never delivers its promised benefit
— why would that be?).
