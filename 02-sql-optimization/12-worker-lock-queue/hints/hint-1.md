# Hint 1

Run the demo (`uv run python 12-worker-lock-queue/src/harness.py --demo`)
with the stock `claim.sql`. While it's running, from a second `psql` (or
any client) connected to the same database, query `pg_stat_activity` for
sessions whose `query` mentions `payments_queue_arena` and look at their
`state` and `wait_event_type`/`wait_event` columns. How many sessions are
actually doing work at any given moment, versus just waiting?

Then join `pg_locks` to `pg_stat_activity` on `pid`, filter to locks on
`payments_queue_arena`, and look at the `granted` column. `SELECT
pg_blocking_pids(pid) FROM pg_stat_activity WHERE pid = <a waiting pid>`
will tell you exactly which other session each blocked worker is waiting
on.
