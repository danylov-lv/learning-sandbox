"""Validator for 12-api-engineering task 04 -- background jobs and idempotency.

Never trusts the app's own numbers: the export aggregate is checked against
an oracle the validator computes with its OWN SQL over the read-only `shop`
schema, straight from `shop.orders`/`shop.order_items`.

Launches the app as a REAL SUBPROCESS (`run_app_subprocess`), not in-process
-- see harness/service.py's rationale: the background worker must be
observable independent of the validator's own event loop, and a learner
solution that accidentally blocks the event loop synchronously should not be
able to freeze the validator itself along with it.

Checks, in order:

  1. POST /exports -> 202 immediately with a job_id (a stub's 501 fails here
     with a clean single-line NOT PASSED, no traceback).
  2. Poll GET /exports/{job_id} until status == "done" (bounded timeout);
     the result must match the independent oracle (money with tolerance).
  3. Idempotency: POST again with the SAME Idempotency-Key -> same job_id,
     and exactly 1 row in t04.jobs for that key.
  4. Isolation: a fresh Idempotency-Key -> a different, independent job_id.
  5. Concurrency (the real test): fire N simultaneous POSTs sharing ONE
     fresh Idempotency-Key; all N responses must carry the SAME job_id AND
     exactly ONE row must exist in t04.jobs for that key. A read-then-write
     idempotency implementation creates duplicates and fails here.

Run from this task's directory:

    uv run python tests/validate.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, pg_conn, run_async  # noqa: E402
from harness.service import run_app_subprocess  # noqa: E402

from src.app import JOBS_SCHEMA  # noqa: E402

POLL_TIMEOUT_SEC = 30.0
POLL_INTERVAL_SEC = 0.25
CONCURRENCY_N = 20
MONEY_TOL = 0.01


def _reset_schema():
    with pg_conn() as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {JOBS_SCHEMA} CASCADE")
        conn.commit()


def _pick_test_user():
    with pg_conn() as conn:
        row = conn.execute(
            "SELECT user_id FROM shop.orders GROUP BY user_id HAVING count(*) > 5 LIMIT 1"
        ).fetchone()
    if not row:
        not_passed("could not find a seeded user with more than 5 orders in shop.orders")
    return int(row[0])


def _oracle_export(user_id):
    with pg_conn() as conn:
        order_count, total_amount = conn.execute(
            "SELECT count(*), COALESCE(SUM(total_amount), 0) FROM shop.orders WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        (item_count,) = conn.execute(
            """
            SELECT COALESCE(SUM(oi.qty), 0)
            FROM shop.order_items oi
            JOIN shop.orders o ON o.id = oi.order_id
            WHERE o.user_id = %s
            """,
            (user_id,),
        ).fetchone()
    return {
        "user_id": user_id,
        "order_count": int(order_count),
        "item_count": int(item_count),
        "total_amount": float(total_amount),
    }


def _count_jobs_for_key(key):
    with pg_conn() as conn:
        (n,) = conn.execute(
            f"SELECT count(*) FROM {JOBS_SCHEMA}.jobs WHERE idempotency_key = %s", (key,)
        ).fetchone()
    return int(n)


def _fresh_key(tag):
    return f"itest-{tag}-{uuid.uuid4().hex[:12]}"


async def _post_export(client, user_id, key):
    return await client.post("/exports", json={"user_id": user_id}, headers={"Idempotency-Key": key})


async def _get_export(client, job_id):
    return await client.get(f"/exports/{job_id}")


async def _poll_until_done(client, job_id, timeout=POLL_TIMEOUT_SEC):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_body = None
    while loop.time() < deadline:
        r = await _get_export(client, job_id)
        if r.status_code != 200:
            not_passed(f"GET /exports/{job_id} returned {r.status_code} while polling: {r.text[:200]!r}")
        body = r.json()
        last_body = body
        status = body.get("status")
        if status == "done":
            return body
        if status == "error":
            not_passed(f"job {job_id} ended in status 'error': {body.get('error')!r}")
        await asyncio.sleep(POLL_INTERVAL_SEC)
    not_passed(f"job {job_id} did not reach status 'done' within {timeout}s (last seen: {last_body!r})")


async def _run_checks(base_url, user_id, oracle):
    import httpx

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        # --- 1+2: basic POST -> 202 -> poll -> result matches oracle ---
        key1 = _fresh_key("basic")
        r = await _post_export(client, user_id, key1)
        if r.status_code != 202:
            not_passed(
                f"POST /exports returned {r.status_code}, expected 202 (immediate accept, no inline "
                f"computation) -- body: {r.text[:200]!r}"
            )
        body = r.json()
        job_id = body.get("job_id")
        if not job_id:
            not_passed(f"POST /exports response missing 'job_id': {body!r}")
        if body.get("status") not in ("queued", "running", "done"):
            not_passed(f"POST /exports response has unexpected status {body.get('status')!r}")

        done_body = await _poll_until_done(client, job_id)
        result = done_body.get("result")
        if not isinstance(result, dict):
            not_passed(f"done job {job_id} has no 'result' object: {done_body!r}")
        for k in ("order_count", "item_count", "total_amount"):
            if k not in result:
                not_passed(f"result missing key {k!r}: {result!r}")
        if int(result["order_count"]) != oracle["order_count"]:
            not_passed(
                f"result.order_count={result['order_count']}, oracle expects {oracle['order_count']} "
                f"(computed independently from shop.orders)"
            )
        if int(result["item_count"]) != oracle["item_count"]:
            not_passed(
                f"result.item_count={result['item_count']}, oracle expects {oracle['item_count']} "
                f"(computed independently from shop.order_items)"
            )
        if abs(float(result["total_amount"]) - oracle["total_amount"]) > MONEY_TOL:
            not_passed(
                f"result.total_amount={result['total_amount']}, oracle expects "
                f"~{oracle['total_amount']} (tol {MONEY_TOL}) -- check for join fan-out double-"
                f"counting shop.orders.total_amount over shop.order_items rows"
            )

        # --- 3: idempotency -- same key again -> same job_id, still 1 row ---
        r2 = await _post_export(client, user_id, key1)
        if r2.status_code != 202:
            not_passed(f"repeat POST with the same Idempotency-Key returned {r2.status_code}, expected 202")
        body2 = r2.json()
        if body2.get("job_id") != job_id:
            not_passed(
                f"repeat POST with the SAME Idempotency-Key returned a DIFFERENT job_id "
                f"({body2.get('job_id')!r} != {job_id!r}) -- idempotency is broken"
            )
        n_rows = _count_jobs_for_key(key1)
        if n_rows != 1:
            not_passed(f"expected exactly 1 row in {JOBS_SCHEMA}.jobs for key {key1!r}, found {n_rows}")

        # --- 4: isolation -- a fresh key is a genuinely different job ---
        key2 = _fresh_key("iso")
        r3 = await _post_export(client, user_id, key2)
        if r3.status_code != 202:
            not_passed(f"POST with a fresh Idempotency-Key returned {r3.status_code}, expected 202")
        job_id2 = r3.json().get("job_id")
        if not job_id2:
            not_passed(f"POST with a fresh Idempotency-Key is missing 'job_id': {r3.json()!r}")
        if job_id2 == job_id:
            not_passed("a DIFFERENT Idempotency-Key produced the SAME job_id as an unrelated key")

        # --- 5: concurrency -- N simultaneous POSTs, ONE shared fresh key ---
        key3 = _fresh_key("conc")

        async def _one():
            return await _post_export(client, user_id, key3)

        responses = await asyncio.gather(*[_one() for _ in range(CONCURRENCY_N)])
        statuses = [r.status_code for r in responses]
        if any(s != 202 for s in statuses):
            not_passed(
                f"concurrent burst of {CONCURRENCY_N} POSTs sharing one Idempotency-Key: not all "
                f"responses were 202 (got {statuses})"
            )
        job_ids = {r.json().get("job_id") for r in responses}
        if len(job_ids) != 1:
            not_passed(
                f"concurrent burst of {CONCURRENCY_N} POSTs with ONE shared Idempotency-Key produced "
                f"{len(job_ids)} distinct job_ids ({sorted(str(j) for j in job_ids)}) -- expected "
                f"exactly 1. The insert-or-fetch is not atomic (a read-then-write race let more than "
                f"one caller create a job for the same fresh key)."
            )
        n_rows3 = _count_jobs_for_key(key3)
        if n_rows3 != 1:
            not_passed(
                f"concurrent burst of {CONCURRENCY_N} POSTs left {n_rows3} rows in {JOBS_SCHEMA}.jobs "
                f"for key {key3!r}, expected exactly 1 -- same atomicity bug, visible directly in the DB"
            )
        await _poll_until_done(client, next(iter(job_ids)))

    return job_id, job_id2


@guarded
def main():
    _reset_schema()
    user_id = _pick_test_user()
    oracle = _oracle_export(user_id)

    try:
        async def _go():
            async with run_app_subprocess(
                "src.app:app",
                env={"PYTHONPATH": str(TASK_ROOT)},
            ) as service:
                return await _run_checks(service.base_url, user_id, oracle)

        job_id, job_id2 = run_async(_go())
    finally:
        _reset_schema()

    passed(
        f"user_id={user_id}: export result matched independent oracle "
        f"(order_count={oracle['order_count']}, item_count={oracle['item_count']}, "
        f"total_amount={oracle['total_amount']:.2f}); idempotent repeat -> same job_id; "
        f"different key -> different job_id ({job_id} vs {job_id2}); "
        f"concurrent burst of {CONCURRENCY_N} POSTs sharing one key -> exactly 1 job"
    )


if __name__ == "__main__":
    main()
