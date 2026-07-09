# Hint 1

Before rewriting anything, make the flood visible. Wrap the psycopg
cursor (or connection) so every `execute()` call is counted or logged, and
call `fetch_dashboard()` once for a user with dozens of orders. How many
`execute()` calls happen? Does that number depend on how many orders the
user has, or is it fixed?

If you'd rather see it at the database level: Postgres's own statement
logging, or thinking in terms of what `pg_stat_statements` would report as
"calls" for this workload, tells the same story — one query shape
executed N times, where N is the order count, instead of executed once.
