Delete-then-insert, concretely: within one psycopg transaction (don't
autocommit between statements), `DELETE FROM staging.price_records_raw WHERE
dt = %s`, then `executemany` the insert for the freshly parsed batch, then
one `conn.commit()` at the very end. If anything raises before that commit,
nothing you did in this transaction persists — Postgres rolls it back for
you as long as you don't commit early and don't open a second connection
partway through.

Upsert, concretely: `INSERT INTO staging.price_records_raw (dt, line_no,
payload) VALUES (%s, %s, %s) ON CONFLICT (dt, line_no) DO UPDATE SET payload
= EXCLUDED.payload, loaded_at = now()`. Since the source file for a given
`dt` never changes between runs in this task, `DO NOTHING` would also pass —
but `DO UPDATE` is the more defensible choice for describing what "rerun a
load" should mean in general (in production, upstream data can change
between runs of the same partition), and it's what you'd want if this task
ever grew a "source file gets corrected upstream" scenario.

For the audit row: wrap the parse-and-write logic in a `try`/`except`.
On success, insert `('success', rows_loaded)`. In the `except` block,
insert `('failed', 0)` (or whatever count you got before the failure) using
a **fresh** connection/transaction if the original one is already broken by
the exception, then re-raise so Airflow still marks the task failed —
recording the failure and letting the task actually fail are not mutually
exclusive.
