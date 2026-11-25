# Hint 2

For idempotency, the upsert into `staging.price_records_raw` should use
`INSERT ... ON CONFLICT (dt, line_no) DO UPDATE` (or `DO NOTHING`, if you
don't care about refreshing `loaded_at`/`payload` on a rerun) — not a plain
`INSERT`, which would violate the primary key on a second run and blow up
the task instead of silently doing nothing.

Retries belong on the `@task` decorator itself: `@task(retries=3,
retry_delay_seconds=2)`. Put them on the tasks that touch the filesystem or
the database, not on a pure-Python parsing step that will fail the same way
every time it's retried.

For `ops.load_audit`, `run_id` doesn't have to come from anywhere fancy — a
`uuid4()` string, or Prefect's own flow-run id if you want to look it up
via `prefect.context`, both satisfy the schema.
