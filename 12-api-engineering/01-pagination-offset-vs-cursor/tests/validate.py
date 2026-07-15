"""Validator for 12-api-engineering task 01 -- pagination-offset-vs-cursor.

Checks the learner's src/app.py against an INDEPENDENT oracle computed
straight from shop.products, plus the relative timing claim the task is
built around:

  1. Launch the app in-process via `run_app` (a real uvicorn server on an
     ephemeral port, not `asgi_client`) -- the scaffold's docstring
     recommends a FastAPI `lifespan` that opens one `pg_pool()`, and only a
     real ASGI server actually runs lifespan startup/shutdown events;
     httpx's in-memory ASGITransport does not, so a pool-based
     implementation would crash under it despite being correct. A stub
     handler answers HTTP 501 (registered exception handler) -> single-line
     NOT PASSED.
  2. Full-catalog sweep: page /products/cursor from the start to exhaustion
     (limit=1000 -> 200 full pages + 1 trailing empty page to observe
     next_cursor=null, kept sane at ~201 requests) and assert every product
     was returned EXACTLY ONCE: count == 200,000 AND the summed id checksum
     == 20,000,100,000 (ground truth `products_id_checksum`, which is
     n*(n+1)/2 since ids are the contiguous 1..200000 range) -- both
     together, since either check alone can be gamed by a buggy pagination.
  3. Several /products/offset pages checked against an oracle the validator
     computes itself via independent SQL against shop.products -- never
     trusting the app's own numbers.
  4. A deep cursor page (cursor=190000) checked against that same kind of
     independent oracle.
  5. Reads pagination-local.json (from baseline.py) and asserts deep-offset
     latency is materially worse than shallow-offset, while cursor latency
     stays flat with depth -- RELATIVE to this machine's own baseline,
     never an absolute millisecond number. Missing baseline -> NOT PASSED
     telling the learner to run baseline.py first.

Run from this task's directory:

    uv run python baseline.py        # once, writes pagination-local.json
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
    load_ground_truth,
    not_passed,
    passed,
    pg_conn,
    read_baseline,
    run_async,
)
from harness.service import run_app  # noqa: E402
from src.app import app  # noqa: E402

BASELINE_PATH = "01-pagination-offset-vs-cursor/pagination-local.json"

SWEEP_LIMIT = 1000  # 200,000 rows / 1000 = 200 pages, ~201 requests with the trailing empty page
SWEEP_MAX_PAGES = 250  # safety cap well above the expected ~201, catches a non-terminating cursor

# (limit, offset) cases checked against an independent SQL oracle, spread
# across shallow/mid/deep and including a short trailing page near the end.
OFFSET_CASES = [(20, 0), (15, 7), (50, 50_000), (100, 150_000), (33, 199_990)]
DEEP_CURSOR_CASE = (50, 190_000)  # (limit, cursor) -- deep keyset page vs. its own oracle

PRICE_TOLERANCE = 0.01
MIN_OFFSET_RATIO = 1.8  # deep-offset / shallow-offset must be at least this much worse
MAX_CURSOR_RATIO = 2.0  # deep-cursor / shallow-cursor must stay close to flat


def _oracle_offset(limit, offset):
    with pg_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, price FROM shop.products ORDER BY id LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
    return [(r[0], r[1], float(r[2])) for r in rows]


def _oracle_cursor(limit, cursor):
    with pg_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, price FROM shop.products WHERE id > %s ORDER BY id LIMIT %s",
            (cursor, limit),
        ).fetchall()
    return [(r[0], r[1], float(r[2])) for r in rows]


def _check_items_match_oracle(ctx, items, oracle_rows):
    if len(items) != len(oracle_rows):
        not_passed(f"{ctx}: got {len(items)} items, oracle expected {len(oracle_rows)}")
    for i, (item, (oid, otitle, oprice)) in enumerate(zip(items, oracle_rows)):
        if not isinstance(item, dict):
            not_passed(f"{ctx}: item {i} is not an object: {item!r}")
        if item.get("id") != oid:
            not_passed(f"{ctx}: item {i} id={item.get('id')!r}, oracle expected {oid}")
        if item.get("title") != otitle:
            not_passed(f"{ctx}: item {i} (id={oid}) title={item.get('title')!r}, oracle expected {otitle!r}")
        price = item.get("price")
        if price is None or abs(float(price) - oprice) > PRICE_TOLERANCE:
            not_passed(f"{ctx}: item {i} (id={oid}) price={price!r}, oracle expected ~{oprice} (tol {PRICE_TOLERANCE})")


async def _get(http, path, params):
    r = await http.get(path, params=params)
    if r.status_code != 200:
        body = r.text.strip().splitlines()
        tail = body[-1] if body else "(empty)"
        not_passed(f"GET {path} params={params} returned HTTP {r.status_code} (handler not implemented?): {tail[:200]}")
    return r


async def _sweep_cursor(http):
    """Page /products/cursor from the start to exhaustion, returning
    (total_items_seen, id_checksum, pages_requested)."""
    seen = 0
    checksum = 0
    cursor = None
    pages = 0
    while True:
        pages += 1
        if pages > SWEEP_MAX_PAGES:
            not_passed(
                f"cursor sweep did not terminate within {SWEEP_MAX_PAGES} pages -- "
                f"check next_cursor logic (must become null once the catalog is exhausted)"
            )
        params = {"limit": SWEEP_LIMIT}
        if cursor is not None:
            params["cursor"] = cursor
        r = await _get(http, "/products/cursor", params)
        body = r.json()
        items = body.get("items")
        if not isinstance(items, list):
            not_passed(f"cursor sweep page {pages}: 'items' missing or not a list in {body!r}")
        for item in items:
            if not isinstance(item, dict) or "id" not in item:
                not_passed(f"cursor sweep page {pages}: malformed item {item!r}")
            seen += 1
            checksum += int(item["id"])
        next_cursor = body.get("next_cursor")
        if not items:
            break
        if next_cursor is None:
            break
        if not isinstance(next_cursor, int) or next_cursor <= (cursor or 0):
            not_passed(
                f"cursor sweep page {pages}: next_cursor={next_cursor!r} is not a larger int than "
                f"the previous cursor ({cursor!r}) -- pagination must advance"
            )
        cursor = next_cursor
    return seen, checksum, pages


async def _main_async():
    async with run_app(app) as svc:
        async with svc.client(timeout=30.0) as http:
            # --- Check (a): full cursor sweep, exactly-once over the whole catalog ---
            seen, checksum, pages = await _sweep_cursor(http)

            gt = load_ground_truth()
            expected_count = gt["row_counts"]["products"]
            expected_checksum = gt["products_id_checksum"]

            if seen != expected_count:
                not_passed(f"cursor sweep returned {seen} products, ground truth expects {expected_count}")
            if checksum != expected_checksum:
                not_passed(
                    f"cursor sweep id checksum {checksum} != ground truth {expected_checksum} -- "
                    f"count matched but some ids were skipped/duplicated"
                )

            # --- Check (b): several /products/offset pages against an independent oracle ---
            for limit, offset in OFFSET_CASES:
                r = await _get(http, "/products/offset", {"limit": limit, "offset": offset})
                body = r.json()
                ctx = f"offset page (limit={limit}, offset={offset})"
                if body.get("limit") != limit:
                    not_passed(f"{ctx}: response 'limit'={body.get('limit')!r}, expected {limit}")
                if body.get("offset") != offset:
                    not_passed(f"{ctx}: response 'offset'={body.get('offset')!r}, expected {offset}")
                items = body.get("items")
                if not isinstance(items, list):
                    not_passed(f"{ctx}: 'items' missing or not a list in {body!r}")
                oracle_rows = _oracle_offset(limit, offset)
                _check_items_match_oracle(ctx, items, oracle_rows)

            # --- Check (c): a deep cursor page against its own independent oracle ---
            limit, cursor = DEEP_CURSOR_CASE
            ctx = f"deep cursor page (limit={limit}, cursor={cursor})"
            r = await _get(http, "/products/cursor", {"limit": limit, "cursor": cursor})
            body = r.json()
            items = body.get("items")
            if not isinstance(items, list):
                not_passed(f"{ctx}: 'items' missing or not a list in {body!r}")
            oracle_rows = _oracle_cursor(limit, cursor)
            _check_items_match_oracle(ctx, items, oracle_rows)
            expected_next = oracle_rows[-1][0] if len(oracle_rows) == limit else None
            if body.get("next_cursor") != expected_next:
                not_passed(f"{ctx}: next_cursor={body.get('next_cursor')!r}, expected {expected_next!r}")

    return seen, checksum, pages


@guarded
def main():
    baseline = read_baseline(BASELINE_PATH)
    if baseline is None:
        not_passed(
            "no pagination baseline found -- run `uv run python baseline.py` first "
            f"to write {BASELINE_PATH} (the deep-vs-shallow timing check is relative to it)"
        )

    seen, checksum, pages = run_async(_main_async())

    # --- Check (d): relative timing -- offset degrades with depth, cursor stays flat ---
    offset_shallow = baseline.get("offset_shallow_ms")
    offset_deep = baseline.get("offset_deep_ms")
    cursor_shallow = baseline.get("cursor_shallow_ms")
    cursor_deep = baseline.get("cursor_deep_ms")
    if not offset_shallow or not offset_deep or not cursor_shallow or not cursor_deep:
        not_passed(f"baseline {BASELINE_PATH} is malformed ({baseline!r}) -- rerun baseline.py")

    offset_ratio = offset_deep / offset_shallow
    cursor_ratio = cursor_deep / cursor_shallow

    if offset_ratio < MIN_OFFSET_RATIO:
        not_passed(
            f"offset pagination only got {offset_ratio:.2f}x slower at depth (shallow "
            f"{offset_shallow:.3f} ms vs deep {offset_deep:.3f} ms), expected at least "
            f"{MIN_OFFSET_RATIO:.1f}x -- is /products/offset really using OFFSET (not secretly "
            f"keyset-seeking)?"
        )
    if cursor_ratio > MAX_CURSOR_RATIO:
        not_passed(
            f"cursor pagination got {cursor_ratio:.2f}x slower at depth (shallow "
            f"{cursor_shallow:.3f} ms vs deep {cursor_deep:.3f} ms), expected it to stay within "
            f"{MAX_CURSOR_RATIO:.1f}x (flat) -- is /products/cursor really seeking via "
            f"`WHERE id > :cursor` and not an OFFSET in disguise?"
        )

    passed(
        f"cursor sweep exact ({seen} products, checksum {checksum}, {pages} pages); "
        f"{len(OFFSET_CASES)} offset pages + 1 deep cursor page correct vs shop oracle; "
        f"offset deep/shallow {offset_ratio:.2f}x, cursor deep/shallow {cursor_ratio:.2f}x"
    )


if __name__ == "__main__":
    main()
