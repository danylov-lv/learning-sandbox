"""s12.t04 -- async export jobs with idempotent enqueueing.

A marketplace "export my order history" button kicks off an expensive
report the client should not block on. The shape:

  POST /exports  {"user_id": <int>}, header "Idempotency-Key: <string>"
      Enqueues a BACKGROUND job that computes the user's order-history
      aggregate from `shop.orders`/`shop.order_items` and returns 202
      IMMEDIATELY, without computing anything inline:
          {"job_id": <str>, "status": "queued"|"running"|"done"}

  GET /exports/{job_id}
      {"job_id": <str>, "status": ..., "result": <dict-or-null>, "error": <str-or-null>}
      `result` is populated once `status == "done"`.

The actual engineering point is IDEMPOTENCY under concurrency:

  - Two POSTs with the SAME Idempotency-Key (whether sequential or fired at
    the exact same instant) must resolve to the SAME job_id -- never two
    rows in `t04.jobs` for one key. A "SELECT, and if nothing found INSERT"
    handler has a race: under N simultaneous requests for a brand-new key,
    every one of them can see "no row yet" before any of them has written
    one, and all N insert. The fix is an ATOMIC insert -- a unique
    constraint plus `INSERT ... ON CONFLICT DO NOTHING RETURNING`, not two
    separate round trips with a decision made in between.
  - A different Idempotency-Key is a genuinely different job -- idempotency
    is scoped to the key, not to the user_id/payload.

This task owns Postgres schema `t04` (JOBS_SCHEMA below, applied
automatically on startup -- see `lifespan`). It writes NOTHING to `shop`
(`shop.orders` / `shop.order_items` are read-only inputs) and does not use
Redis; Postgres's own unique constraint is the entire idempotency mechanism
here.

Reaching Postgres: this module inserts the module root onto `sys.path`
itself (see below) so `harness.common` (`pg_conn`, `pg_pool`) is importable
whether this app is launched in-process or as a real subprocess by the
validator. These are synchronous clients -- calling them from async route
handlers, or from a background task, is the accepted pattern in this module
(a sync function handed to `BackgroundTasks.add_task` runs in a thread pool
automatically, so it does not block the event loop while it waits on
Postgres).
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from harness.common import pg_conn  # noqa: E402

# --------------------------------------------------------------------------
# Fixed contract constants -- the validator imports JOBS_SCHEMA.
# --------------------------------------------------------------------------

JOBS_SCHEMA = "t04"

# Given as guidance/boilerplate, not the exercise: the DDL for this task's
# own schema. The UNIQUE constraint on idempotency_key is what makes an
# atomic INSERT ... ON CONFLICT possible in get_or_create_job() below --
# using it is part of the "your choice" the README offers, but the actual
# atomic-insert-or-fetch LOGIC is still yours to write.
SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {JOBS_SCHEMA};

CREATE TABLE IF NOT EXISTS {JOBS_SCHEMA}.jobs (
    job_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key  TEXT NOT NULL UNIQUE,
    user_id          INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'done', 'error')),
    result           JSONB,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class ExportRequest(BaseModel):
    user_id: int


# --------------------------------------------------------------------------
# App wiring (given) -- applies SCHEMA_SQL on boot so t04.jobs always exists
# before the first request lands, including right after a validator's
# `DROP SCHEMA t04 CASCADE` on setup.
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    with pg_conn() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()
    yield


app = FastAPI(title="s12.t04 export jobs", lifespan=lifespan)


@app.exception_handler(NotImplementedError)
async def _not_implemented(request, exc):
    return JSONResponse(
        status_code=501,
        content={"detail": "endpoint not implemented yet -- implement it in src/app.py"},
    )


# --------------------------------------------------------------------------
# You implement everything below this line.
# --------------------------------------------------------------------------

def get_or_create_job(user_id: int, idempotency_key: str) -> dict:
    """Atomically look up-or-create the `t04.jobs` row for `idempotency_key`.

    THIS is the engineering point of the task. Return
    `{"job_id": <str>, "status": <str>, "created": <bool>}`.

    Required shape: ONE atomic `INSERT ... ON CONFLICT (idempotency_key) DO
    NOTHING RETURNING job_id, status` -- never a `SELECT` to check for an
    existing row followed by a conditional `INSERT`. If the INSERT returns a
    row, this call just created the job (`created=True`); if it returns
    nothing (conflict), a follow-up `SELECT ... WHERE idempotency_key = %s`
    fetches the row that some other/earlier call already created
    (`created=False`). See the hints for why "insert first, ask questions
    later" is what survives N simultaneous callers with the same fresh key
    -- exactly ONE of them may ever see `created=True`.

    `job_id` must come back as a plain `str` (cast Postgres's UUID value),
    since it has to serialize straight into a JSON response.
    """
    raise NotImplementedError


def compute_export(user_id: int) -> dict:
    """Compute the order-history export aggregate for `user_id` from the
    READ-ONLY `shop` schema. Return:

        {"user_id": user_id,
         "order_count": <int, DISTINCT orders for this user>,
         "item_count": <int, SUM(order_items.qty) across this user's orders>,
         "total_amount": <float, SUM(orders.total_amount) for this user>}

    Pitfall: `total_amount` lives on `shop.orders`, one value per order --
    not on `shop.order_items`. A single query that JOINs orders to
    order_items and then sums `orders.total_amount` over the JOINED rows
    will over-count every order that has more than one line item (that
    column gets summed once per matched item row, not once per order).
    Compute `order_count`/`total_amount` straight from `shop.orders` (no
    join needed for those two), and `item_count` from a join/aggregate
    against `shop.order_items` -- don't sum a per-order column over a
    per-item join.
    """
    raise NotImplementedError


def run_export_job(job_id: str, user_id: int) -> None:
    """The background job body: compute the export and durably record the
    outcome on `t04.jobs`.

    - Mark the job `status = 'running'` (an UPDATE by job_id).
    - Call `compute_export(user_id)`.
    - On success: write `result` (as JSON -- wrap the dict with
      `psycopg.types.json.Jsonb(...)` when passing it as a query parameter,
      a bare `dict` does not serialize correctly into a `jsonb` column) and
      set `status = 'done'`.
    - On any exception from `compute_export`: set `status = 'error'` and
      `error = str(exc)`. Never let an exception escape this function
      uncaught -- there's nothing downstream to catch it (this runs as a
      background task, after the HTTP response has already been sent).
    """
    raise NotImplementedError


@app.post("/exports", status_code=202)
async def create_export(
    payload: ExportRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Enqueue an export job idempotently and return immediately.

    1. Call `get_or_create_job(payload.user_id, idempotency_key)`.
    2. If it just created the job (`created=True`), schedule
       `run_export_job(job_id, payload.user_id)` via
       `background_tasks.add_task(...)` -- this is what makes the response
       come back before the aggregate is computed. If the job already
       existed (`created=False`), do NOT schedule anything again; whoever
       created it already enqueued (or already finished) the work.
    3. Respond `202` with `{"job_id", "status"}` using the row's current
       status either way.

    A missing `Idempotency-Key` header is rejected by FastAPI itself (422)
    before this function ever runs -- no special handling needed here.
    """
    raise NotImplementedError


@app.get("/exports/{job_id}")
async def get_export(job_id: str):
    """Return the current state of `job_id`.

    `200` with `{"job_id", "status", "result", "error"}`. `result` is `null`
    until `status == "done"` (then the dict `compute_export` produced,
    round-tripped through `jsonb`); `error` is `null` unless
    `status == "error"`. Unknown `job_id` -> `raise HTTPException(404, ...)`.
    """
    raise NotImplementedError
