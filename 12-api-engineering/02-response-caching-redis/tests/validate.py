"""Validator for 12-api-engineering task 02 -- response-caching-redis.

Checks the learner's src/app.py caching endpoint against an INDEPENDENT
oracle and the observable cache contract from the README:

  1. Launch the app (in-process, ephemeral port). A stub handler returns
     HTTP 500 -> single-line NOT PASSED.
  2. redis_flush_prefix(client, "s12:t02:") on setup (idempotent -- a crashed
     prior run never blocks a fresh one).
  3. Correctness: for several leaf categories, the endpoint's summary must
     equal the validator's OWN oracle computed straight from shop.products
     (count, sum, avg with float tolerance). The app's own numbers are never
     trusted.
  4. Cache engages: first GET reports X-Cache: MISS and creates the Redis key
     s12:t02:summary:<id>; second GET reports X-Cache: HIT and the key is
     still there.
  5. Invalidation: after POST .../invalidate the Redis key is gone and the
     next GET is a MISS again.
  6. Cache fidelity: the HIT body is byte-for-byte identical to the MISS body
     that populated the cache (no corrupted / re-serialized-wrong value).
  7. Relative speedup: reads caching-local.json (from baseline.py) and asserts
     HIT is materially faster than MISS on THIS machine. Never absolute.

Always flushes the s12:t02: prefix on the way out. Run from this task's dir:

    uv run python baseline.py        # once, writes caching-local.json
    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    not_passed,
    passed,
    pg_conn,
    read_baseline,
    redis_client,
    redis_flush_prefix,
    run_async,
)
from harness.service import run_app  # noqa: E402
from src.app import CACHE_PREFIX, app  # noqa: E402

TASK_PREFIX = "s12:t02:"
CATEGORY_IDS = [9, 20, 40, 55]  # leaf categories with products, spread across the Zipf tail
PRICE_TOLERANCE = 0.01
BASELINE_PATH = "02-response-caching-redis/caching-local.json"
MIN_SPEEDUP = 3.0  # HIT must be at least this many times faster than MISS


def _oracle(category_id):
    """Compute the true summary for a leaf category directly from shop."""
    with pg_conn() as conn:
        row = conn.execute(
            "SELECT count(*)::bigint, "
            "COALESCE(sum(price), 0)::double precision, "
            "avg(price)::double precision "
            "FROM shop.products WHERE category_id = %s",
            (category_id,),
        ).fetchone()
    return {"product_count": int(row[0]), "price_sum": float(row[1]), "avg_price": row[2]}


def _summary_key(category_id):
    return f"{CACHE_PREFIX}{category_id}"


def _check_field(ctx, name, got, expected, tolerance=None):
    if tolerance is not None:
        if got is None or abs(float(got) - float(expected)) > tolerance:
            not_passed(f"{ctx}: {name} = {got!r}, oracle expected ~{expected} (tol {tolerance})")
    else:
        if got != expected:
            not_passed(f"{ctx}: {name} = {got!r}, oracle expected {expected!r}")


async def _get(http, category_id):
    r = await http.get(f"/categories/{category_id}/summary")
    if r.status_code != 200:
        body = r.text.strip().splitlines()
        tail = body[-1] if body else "(empty)"
        not_passed(
            f"GET /categories/{category_id}/summary returned HTTP {r.status_code} "
            f"(handler not implemented?): {tail[:200]}"
        )
    return r


async def _main_async(rclient):
    checked = 0
    async with run_app(app) as svc:
        async with svc.client(timeout=30.0) as http:
            for category_id in CATEGORY_IDS:
                key = _summary_key(category_id)
                redis_flush_prefix(rclient, TASK_PREFIX)  # ensure a clean MISS per category

                oracle = _oracle(category_id)
                if oracle["product_count"] == 0:
                    not_passed(f"test category {category_id} unexpectedly has 0 products -- pick another")

                # --- Check 4a: first GET is a MISS and populates the key ---
                r_miss = await _get(http, category_id)
                if r_miss.headers.get("X-Cache") != "MISS":
                    not_passed(
                        f"category {category_id}: first GET after invalidation reported "
                        f"X-Cache={r_miss.headers.get('X-Cache')!r}, expected MISS"
                    )
                if not rclient.exists(key):
                    not_passed(f"category {category_id}: MISS did not create the Redis key {key}")

                # --- Check 3: correctness against the independent oracle ---
                body = r_miss.json()
                ctx = f"category {category_id}"
                _check_field(ctx, "category_id", body.get("category_id"), category_id)
                _check_field(ctx, "product_count", body.get("product_count"), oracle["product_count"])
                _check_field(ctx, "price_sum", body.get("price_sum"), oracle["price_sum"], PRICE_TOLERANCE)
                _check_field(ctx, "avg_price", body.get("avg_price"), oracle["avg_price"], PRICE_TOLERANCE)

                # --- Check 4b + 6: second GET is a HIT, key persists, body byte-identical ---
                r_hit = await _get(http, category_id)
                if r_hit.headers.get("X-Cache") != "HIT":
                    not_passed(
                        f"category {category_id}: second GET reported "
                        f"X-Cache={r_hit.headers.get('X-Cache')!r}, expected HIT"
                    )
                if not rclient.exists(key):
                    not_passed(f"category {category_id}: Redis key {key} vanished after a HIT")
                if r_hit.content != r_miss.content:
                    not_passed(
                        f"category {category_id}: HIT body differs from the MISS body that "
                        f"populated the cache -- a HIT must serve the stored bytes unchanged"
                    )

                # --- Check 5: invalidation drops the key, next GET is a MISS ---
                r_inv = await http.post(f"/categories/{category_id}/invalidate")
                if r_inv.status_code != 200:
                    not_passed(
                        f"category {category_id}: POST invalidate returned HTTP {r_inv.status_code}, expected 200"
                    )
                if rclient.exists(key):
                    not_passed(f"category {category_id}: Redis key {key} still present after invalidate")
                r_again = await _get(http, category_id)
                if r_again.headers.get("X-Cache") != "MISS":
                    not_passed(
                        f"category {category_id}: GET after invalidate reported "
                        f"X-Cache={r_again.headers.get('X-Cache')!r}, expected MISS (recompute)"
                    )

                checked += 1
    return checked


@guarded
def main():
    rclient = redis_client()
    redis_flush_prefix(rclient, TASK_PREFIX)  # idempotent setup

    baseline = read_baseline(BASELINE_PATH)
    if baseline is None:
        not_passed(
            "no caching baseline found -- run `uv run python baseline.py` first "
            f"to write {BASELINE_PATH} (the speedup check is relative to it)"
        )

    try:
        checked = run_async(_main_async(rclient))
    finally:
        redis_flush_prefix(rclient, TASK_PREFIX)

    miss = baseline.get("miss_ms")
    hit = baseline.get("hit_ms")
    if not miss or not hit or hit <= 0:
        not_passed(f"baseline {BASELINE_PATH} is malformed (miss_ms={miss}, hit_ms={hit}) -- rerun baseline.py")
    speedup = miss / hit
    if speedup < MIN_SPEEDUP:
        not_passed(
            f"cache speedup only {speedup:.1f}x (MISS {miss:.3f} ms vs HIT {hit:.3f} ms) -- "
            f"expected the HIT path to be at least {MIN_SPEEDUP:.0f}x faster; "
            f"is the HIT path really skipping Postgres?"
        )

    passed(
        f"{checked} categories correct vs shop oracle; MISS/HIT/invalidate cache "
        f"contract holds; speedup {speedup:.1f}x (MISS {miss:.3f} ms -> HIT {hit:.3f} ms)"
    )


if __name__ == "__main__":
    main()
