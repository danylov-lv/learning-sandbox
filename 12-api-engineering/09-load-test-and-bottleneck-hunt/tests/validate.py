"""Validator for 12-api-engineering task 09 -- load-test-and-bottleneck-hunt.

Two phases, in order, over the SAME running app instance:

  1. CORRECTNESS FIRST. `GET /catalog/{category_id}` responses are checked
     against an oracle the validator computes itself with independent SQL
     (a JOIN straight over shop.products/shop.sellers) -- never trusting the
     app's own numbers. A "fix" that returns wrong, missing, or extra rows
     fails here regardless of how fast it is. Covers: a large category at
     shallow and deep offsets, a small category's trailing partial page, an
     empty (root) category, and limit/offset clamping of bad params.
  2. RELATIVE THROUGHPUT. Only if correctness passes: the app is bombarded
     with the SAME load shape `baseline.py` used (same URL, concurrency,
     duration) via `harness.load.bombard()`, and the result is compared
     against `catalog-load-local.json` (written by `baseline.py` against the
     STOCK app on this machine). Asserts BOTH an RPS ratio and a p95 ratio
     against that baseline -- RELATIVE to this machine, never an absolute
     millisecond/RPS number (timing is never absolute in this module). If
     the baseline file is missing, tells the learner to run baseline.py
     first instead of crashing.

The app is launched as a REAL SUBPROCESS via `run_app_subprocess` -- see
`baseline.py`'s docstring for why (this task is about an OS-level/event-loop
bottleneck; an in-process launch sharing the validator's own event loop
would hide it).

Run from this task's directory:

    uv run python baseline.py        # once, against the STOCK app
    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, pg_conn, read_baseline, run_async  # noqa: E402
from harness.load import bombard  # noqa: E402
from harness.service import run_app_subprocess  # noqa: E402

BASELINE_PATH = "09-load-test-and-bottleneck-hunt/catalog-load-local.json"

# Must match baseline.py exactly -- the RPS/p95 ratio is only meaningful if
# both runs bombard the identical URL under the identical load shape.
CATEGORY_ID = 9
LIMIT = 30
OFFSET = 0
CONCURRENCY = 30
WARMUP_REQUESTS = 10
DURATION_S = 6.0

# Thresholds picked from measurements on the authoring machine: the stock
# app clears well under 1x its own baseline (by construction -- it hasn't
# changed), and a genuine application-layer fix reached several times the
# stock rps with p95 latency cut to a small fraction of it. Both thresholds
# below sit with real headroom under that measured result, so a correct fix
# on a slower machine still passes, while a superficial change that leaves
# the app still bottlenecked under concurrency will not.
MIN_RPS_RATIO = 4.5
MAX_P95_RATIO = 0.5

PRICE_TOLERANCE = 0.01

# (category_id, limit, offset) cases checked against an independent SQL
# oracle: a large category at a shallow and a deep offset, a small
# category's trailing partial page, an empty (root) category.
CORRECTNESS_CASES = [
    (9, 20, 0),
    (9, 50, 100_000),
    (60, 30, 650),  # category 60 has 673 products -- partial trailing page
    (1, 10, 0),  # category 1 is a ROOT category -- 0 products, always
]


def _oracle_catalog(category_id, limit, offset):
    with pg_conn() as conn:
        rows = conn.execute(
            "SELECT p.id, p.title, p.price, s.name, s.tier FROM shop.products p "
            "JOIN shop.sellers s ON s.id = p.seller_id "
            "WHERE p.category_id = %s ORDER BY p.id LIMIT %s OFFSET %s",
            (category_id, limit, offset),
        ).fetchall()
    return [(r[0], r[1], float(r[2]), r[3], r[4]) for r in rows]


async def _get(http, category_id, params):
    r = await http.get(f"/catalog/{category_id}", params=params)
    if r.status_code != 200:
        body = r.text.strip().splitlines()
        tail = body[-1] if body else "(empty)"
        not_passed(
            f"GET /catalog/{category_id} params={params} returned HTTP {r.status_code} "
            f"(handler broken?): {tail[:200]}"
        )
    return r


def _check_items_match_oracle(ctx, items, oracle_rows):
    if len(items) != len(oracle_rows):
        not_passed(f"{ctx}: got {len(items)} items, oracle expected {len(oracle_rows)}")
    for i, (item, (oid, otitle, oprice, oseller, otier)) in enumerate(zip(items, oracle_rows)):
        if not isinstance(item, dict):
            not_passed(f"{ctx}: item {i} is not an object: {item!r}")
        if item.get("id") != oid:
            not_passed(f"{ctx}: item {i} id={item.get('id')!r}, oracle expected {oid}")
        if item.get("title") != otitle:
            not_passed(f"{ctx}: item {i} (id={oid}) title={item.get('title')!r}, oracle expected {otitle!r}")
        price = item.get("price")
        if price is None or abs(float(price) - oprice) > PRICE_TOLERANCE:
            not_passed(f"{ctx}: item {i} (id={oid}) price={price!r}, oracle expected ~{oprice} (tol {PRICE_TOLERANCE})")
        if item.get("seller_name") != oseller:
            not_passed(f"{ctx}: item {i} (id={oid}) seller_name={item.get('seller_name')!r}, oracle expected {oseller!r}")
        if item.get("seller_tier") != otier:
            not_passed(f"{ctx}: item {i} (id={oid}) seller_tier={item.get('seller_tier')!r}, oracle expected {otier!r}")


async def _check_correctness(http):
    for category_id, limit, offset in CORRECTNESS_CASES:
        r = await _get(http, category_id, {"limit": limit, "offset": offset})
        body = r.json()
        ctx = f"catalog(category_id={category_id}, limit={limit}, offset={offset})"
        if body.get("category_id") != category_id:
            not_passed(f"{ctx}: response 'category_id'={body.get('category_id')!r}, expected {category_id}")
        items = body.get("items")
        if not isinstance(items, list):
            not_passed(f"{ctx}: 'items' missing or not a list in {body!r}")
        oracle_rows = _oracle_catalog(category_id, limit, offset)
        _check_items_match_oracle(ctx, items, oracle_rows)

    # Bad-param clamping: negative limit and an absurdly large one must not
    # reach Postgres as-is, and must not 500.
    r = await _get(http, 9, {"limit": -5, "offset": 0})
    body = r.json()
    if not (1 <= body.get("limit", -1) <= 100):
        not_passed(f"catalog(limit=-5): response 'limit'={body.get('limit')!r} was not clamped into [1, 100]")
    r = await _get(http, 9, {"limit": 999999, "offset": 0})
    body = r.json()
    if not (1 <= body.get("limit", -1) <= 100):
        not_passed(f"catalog(limit=999999): response 'limit'={body.get('limit')!r} was not clamped into [1, 100]")
    if len(body.get("items", [])) > 100:
        not_passed(f"catalog(limit=999999): returned {len(body.get('items'))} items -- limit was not enforced server-side")


async def _measure(base_url):
    url = base_url + f"/catalog/{CATEGORY_ID}?limit={LIMIT}&offset={OFFSET}"
    await bombard(url, concurrency=1, requests=WARMUP_REQUESTS)
    return await bombard(url, concurrency=CONCURRENCY, duration_s=DURATION_S)


async def _main_async():
    async with run_app_subprocess(
        "src.app:app", env={"PYTHONPATH": str(TASK_ROOT)}
    ) as svc:
        async with svc.client(timeout=30.0) as http:
            await _check_correctness(http)
        result = await _measure(svc.base_url)
    return result


@guarded
def main():
    baseline = read_baseline(BASELINE_PATH)
    if baseline is None:
        not_passed(
            "no load baseline found -- run `uv run python baseline.py` first "
            f"(against the STOCK app) to write {BASELINE_PATH}; the relative "
            f"throughput check is meaningless without it"
        )
    for key, expected in (
        ("category_id", CATEGORY_ID),
        ("limit", LIMIT),
        ("offset", OFFSET),
        ("concurrency", CONCURRENCY),
    ):
        if baseline.get(key) != expected:
            not_passed(
                f"baseline {BASELINE_PATH} was recorded with {key}={baseline.get(key)!r}, "
                f"this validator expects {expected!r} -- rerun baseline.py (its load shape "
                f"must match this validator's)"
            )

    result = run_async(_main_async())

    stock_rps = baseline.get("rps")
    stock_p95 = baseline.get("p95_ms")
    if not stock_rps or not stock_p95:
        not_passed(f"baseline {BASELINE_PATH} is malformed ({baseline!r}) -- rerun baseline.py")

    rps_ratio = result.rps / stock_rps
    p95_ratio = result.p95_ms / stock_p95 if stock_p95 > 0 else float("inf")

    print(
        f"stock:  rps={stock_rps:.1f}, p95={stock_p95:.1f} ms\n"
        f"yours:  rps={result.rps:.1f}, p95={result.p95_ms:.1f} ms "
        f"({result.ok} ok / {result.errors} errors of {result.total})\n"
        f"ratio:  rps {rps_ratio:.2f}x, p95 {p95_ratio:.2f}x"
    )

    if result.errors:
        not_passed(f"{result.errors} of {result.total} requests errored during the load test")

    if rps_ratio < MIN_RPS_RATIO:
        not_passed(
            f"throughput only {rps_ratio:.2f}x the stock baseline ({result.rps:.1f} rps vs "
            f"{stock_rps:.1f} rps stock), expected at least {MIN_RPS_RATIO:.1f}x -- the app is "
            f"still too slow under concurrent load"
        )
    if p95_ratio > MAX_P95_RATIO:
        not_passed(
            f"p95 latency only improved to {p95_ratio:.2f}x the stock baseline ({result.p95_ms:.1f} ms "
            f"vs {stock_p95:.1f} ms stock), expected at most {MAX_P95_RATIO:.1f}x -- tail latency is "
            f"still blowing up under concurrency"
        )

    passed(
        f"correctness matched independent oracle on {len(CORRECTNESS_CASES)} cases + clamping; "
        f"throughput {rps_ratio:.2f}x stock ({result.rps:.1f} vs {stock_rps:.1f} rps), "
        f"p95 {p95_ratio:.2f}x stock ({result.p95_ms:.1f} vs {stock_p95:.1f} ms)"
    )


if __name__ == "__main__":
    main()
