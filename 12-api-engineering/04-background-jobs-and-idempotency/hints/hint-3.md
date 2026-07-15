# Hint 3 -- concrete shape

Enough detail to implement `get_or_create_job` without hunting for a
snippet.

**The atomic insert-or-fetch.** One statement:

```
INSERT INTO t04.jobs (idempotency_key, user_id, status)
VALUES (%s, %s, 'queued')
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING job_id, status;
```

- If this returns a row: you just created the job. `created = True`. This is
  the ONLY place a job row is ever created, and Postgres guarantees at most
  one caller, among any number racing on the same fresh key, gets a row back
  from this exact statement.
- If it returns nothing (the `ON CONFLICT ... DO NOTHING` fired -- someone
  else's insert for this key already committed, possibly microseconds
  earlier, possibly a request that finished last week): follow up with
  `SELECT job_id, status FROM t04.jobs WHERE idempotency_key = %s` to fetch
  what the winner created. `created = False`.

Notice this needs no application-level locking, no `SELECT ... FOR UPDATE`,
no retry loop -- the `UNIQUE` constraint plus `ON CONFLICT` is doing all the
serialization, inside Postgres, in one round trip. Twenty concurrent callers
running this exact two-step (insert-attempt, then conditionally select) for
the same key will always converge on the same `job_id`: nineteen of them get
nothing back from the INSERT and fall through to the SELECT, which reads
whatever the twentieth (the actual winner, whichever one Postgres happened
to serialize first) committed.

**Wiring the response.** In the route handler: call `get_or_create_job`.
Only if `created` is `True`, hand `run_export_job` to
`background_tasks.add_task(...)` -- if `created` is `False`, the winner
already scheduled it (or it's further along/done), so scheduling it again
would run `compute_export` a second time for no reason. Respond `202` with
`{"job_id", "status"}` regardless of which branch you took.

**The job runner.** `run_export_job(job_id, user_id)` needs its own
Postgres connection (it runs outside the request's connection lifetime,
possibly in FastAPI's background thread pool). Something like: `UPDATE
t04.jobs SET status='running', updated_at=now() WHERE job_id=%s`, then call
`compute_export(user_id)`, then `UPDATE t04.jobs SET status='done',
result=%s, updated_at=now() WHERE job_id=%s` -- wrap the result dict with
`psycopg.types.json.Jsonb(...)` when passing it as the `result` parameter,
or it won't land in the `jsonb` column as real JSON. Wrap the whole body in
a `try/except` that, on any exception, writes `status='error'`,
`error=str(exc)` instead -- there is nothing above this function to catch a
stray exception, since it runs detached from any request.

**Polling.** `GET /exports/{job_id}` is a single `SELECT ... WHERE
job_id=%s`; nothing clever needed there. A client (and the validator) polls
it in a small loop with a short sleep between attempts and a generous
overall timeout -- `status` transitions `queued -> running -> done` (or
`error`) are all it needs to watch for.

Not spelled out on purpose: the exact SQL for `compute_export`'s three
numbers (see its docstring for the one join-fan-out trap to avoid), and
whether you reach for `BackgroundTasks` or a bare `asyncio.create_task` --
both satisfy the contract; the tradeoffs between them are worth knowing but
not graded here.
