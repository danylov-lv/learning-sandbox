# 04 -- Background Jobs and Idempotency

## Backstory

The marketplace wants an "export my order history" button on the account
page. Clicking it should feel instant -- but computing the export means
scanning a user's full order history and aggregating it, and the client
should never sit on an open HTTP connection waiting for that. The right
shape is: accept the request, hand back a job id right away, and let the
client poll for the result.

That's the easy half. The half that actually matters at this layer: the
button is a button, and buttons get double-clicked, and network requests get
retried by well-behaved clients that never got a response the first time.
Every one of those must resolve to the SAME export job -- never a second one
quietly computing the same thing twice. And it's not enough for that to hold
"most of the time" under a gentle sequential retry; it has to hold when a
burst of identical requests lands at the exact same instant, which is
exactly the shape a retrying client (or an impatient user hammering the
button) produces. A limiter that merely "usually" avoids duplicates under
concurrency is not idempotent, it's lucky.

## What's given

- `src/app.py` -- a FastAPI `app` with:
  - `JOBS_SCHEMA = "t04"` -- this task's own Postgres schema name. The
    validator imports it.
  - `SCHEMA_SQL` -- the DDL for `t04.jobs` (one table: `job_id`,
    `idempotency_key` **UNIQUE**, `user_id`, `status`, `result`, `error`,
    timestamps). Applied automatically on startup via the app's `lifespan`
    -- you don't need to wire schema creation yourself, it's already there
    and re-runs safely every time the app boots.
  - `ExportRequest` -- the Pydantic body model for `POST /exports`.
  - A registered `NotImplementedError` -> `501` exception handler (like
    tasks 01/03), so the stub app imports and launches fine; every
    unimplemented route just answers 501 until you fill it in.
  - Three stubbed functions and two stubbed routes, `raise NotImplementedError`
    with the full contract in their docstrings: `get_or_create_job`,
    `compute_export`, `run_export_job`, `POST /exports`, `GET
    /exports/{job_id}`.
- The shared harness: `harness.common` (`pg_conn`, `pg_pool`) for Postgres.
  `src/app.py` already puts the module root on `sys.path` itself, so
  `harness` imports correctly whether the app is launched in-process or as a
  standalone subprocess.
- The read-only `shop` schema (Postgres, port 54312) -- `shop.orders` and
  `shop.order_items` are all this task reads from `shop`. Nothing is ever
  written back to `shop`.
- This task does not use Redis. The idempotency mechanism here is entirely a
  Postgres unique constraint; there is no `s12:t04:` Redis prefix to worry
  about.

## What's required

### `POST /exports`

Header: `Idempotency-Key: <non-empty string>` -- required (a missing header
is rejected by FastAPI's own validation, 422, before your code runs).
Body: `{"user_id": int}`.

Must **enqueue a background job and return immediately** -- `202` with
`{"job_id", "status"}`, without computing the export inline. Two requests
carrying the **same** `Idempotency-Key` must resolve to the **same**
`job_id`; the mechanism has to be an atomic Postgres insert (a unique
constraint plus `INSERT ... ON CONFLICT DO NOTHING RETURNING`), never a
"check if a row exists, then insert" pair of round trips -- under N
requests hitting a brand-new key at once, that pattern lets every one of
them see "no row yet" and all N insert. A different `Idempotency-Key` for
the same (or a different) `user_id` is a genuinely new, independent job.

### `GET /exports/{job_id}`

`200` with `{"job_id", "status", "result", "error"}`. `status` is one of
`"queued"`, `"running"`, `"done"`, `"error"`. `result` is `null` until
`status == "done"`, at which point it is the computed export:

```
{"user_id", "order_count", "item_count", "total_amount"}
```

- `order_count` -- count of that user's rows in `shop.orders`.
- `item_count` -- sum of `qty` across that user's rows in
  `shop.order_items` (joined via `shop.orders`).
- `total_amount` -- sum of `total_amount` across that user's rows in
  `shop.orders` -- **not** re-derived from `order_items`, and **not**
  summed once per joined item row (a naive single JOIN query that sums
  `orders.total_amount` over item-joined rows over-counts every order that
  has more than one line item). See `compute_export`'s docstring.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It launches your app as a real subprocess, then checks: a `POST /exports`
returns `202` immediately; polling `GET /exports/{job_id}` eventually
reaches `"done"` with a `result` matching the validator's own independent
SQL over `shop`; a repeat `POST` with the same `Idempotency-Key` returns the
same `job_id` with exactly one row in `t04.jobs` for that key; a fresh key
produces a genuinely different job; and -- the real test -- **20 concurrent
POSTs sharing one fresh `Idempotency-Key`** all come back with the SAME
`job_id`, with exactly one row in `t04.jobs` to show for it. It prints
`PASSED` with a short summary, or `NOT PASSED: <reason>` and exits 1
(including on the unimplemented stub). `t04` is dropped and recreated
(by your app's own startup) on setup, and dropped again on teardown.

## Estimated evenings

1-2

## Topics to read up on

- Idempotency keys: the exact semantics real payment/job APIs use (same key
  -> same result, every time it's replayed)
- Atomic upsert in Postgres: `UNIQUE` constraints + `INSERT ... ON CONFLICT
  DO NOTHING/DO UPDATE ... RETURNING`
- Check-then-act race conditions -- the same class of bug as task 03's
  rate limiter, applied to "does this row already exist" instead of "is
  this counter under the limit"
- `BackgroundTasks` vs. a detached `asyncio.create_task` -- what runs when,
  and where each one's exceptions go if you don't catch them
- Status-polling APIs (`queued -> running -> done`) as the simplest shape
  for "the client shouldn't block on this"
- `psycopg`'s `Jsonb` wrapper for writing a Python `dict` into a `jsonb`
  column

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the corpus ground truth, and the verification philosophy behind every task in
this module -- spoilers. Don't read it before finishing this task.
