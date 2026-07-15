"""Validator for 12-api-engineering task 05 -- streaming-large-exports.

Checks the learner's src/app.py export endpoint against an INDEPENDENT
oracle and, critically, against a MEMORY-SHAPE requirement that a "just
wrap it in StreamingResponse" implementation cannot pass:

  1. Launch the app (in-process, real ephemeral socket via harness.service.
     run_app -- a real HTTP connection matters here, see below). A stub
     handler raises NotImplementedError -> HTTP 500 -> single-line
     NOT PASSED.
  2. Correctness (small export): GET /export/products?category_id=<a small
     leaf category> and drain it fully. Assert row COUNT and id CHECKSUM and
     price SUM all match an oracle computed with independent SQL against
     shop.products directly -- never trusting the app's own numbers. Count
     and checksum together are what actually prove "every row exactly once,
     no duplicates, no gaps" (see .authoring/design.md); either alone can be
     gamed by a buggy sweep that happens to sum right.
  3. Correctness (full export): GET /export/products (no filter) and drain
     it fully. Same three checks, this time against the committed
     load_ground_truth() (row_counts.products, products_id_checksum,
     products_price_sum) -- the full catalog's oracle needs no live query.
  4. Ordering: ids seen must be strictly increasing (catches an unordered or
     duplicated sweep even before the checksum comparison would).
  5. THE MEMORY CHECK: both drains above are measured with
     measure_peak_memory (tracemalloc peak, real bytes traced during the
     whole request/response cycle -- server AND client run in the same
     process here, which is exactly what makes this discriminate). The
     small export is ~medium hundreds of rows; the full export is ~300x
     more rows. A real streaming chain (server-side cursor / chunked fetch
     -> generator -> StreamingResponse, client reading incrementally) holds
     a bounded batch at a time regardless of total row count, so peak
     memory should barely move between the two sizes. An implementation
     that materializes the full result (fetchall(), or building the whole
     NDJSON body as one string/list before returning it -- with or without
     a StreamingResponse wrapper) allocates proportionally to row count, so
     its peak grows roughly with the row-count ratio. The check asserts the
     peak ratio stays under MAX_PEAK_RATIO, which is set well below the
     ~300x row-count ratio but with headroom above the near-1x a real
     streaming implementation shows (see NOTES.md / module authoring notes
     for the measured numbers on the reference machine).

     Why measure_peak_memory + run_app (real socket) and not asgi_client:
     httpx's ASGITransport drives the whole ASGI call in-process without a
     real socket, which is fine for shape/content checks, but this task
     specifically needs the DB-facing side of the chain to be honest about
     when it allocates. A real TCP connection via run_app plus a genuinely
     incremental httpx `.stream()`/`aiter_lines()` client read is what
     forces "does the server hand you the first line before it has
     computed the rest" to actually matter for the measured peak, not just
     for wall-clock ordering. Both server and client run in this same
     Python process either way (run_app runs uvicorn in-process on this
     event loop), so tracemalloc's peak over the whole request is a fair
     stand-in for "how much did serving this export cost the process."

  Each measured drain runs in its OWN run_app instance (measure_peak_memory
  takes a SYNC callable; each call wraps run_async(_drain(...)), and
  run_async's asyncio.run needs no event loop already running -- see
  harness/common.py) rather than sharing one long-lived server across both
  measurements, so nothing from the first request's memory carries into the
  second.

Never touches shop except read-only SELECTs; this task owns no Postgres
schema and no Redis prefix (nothing to flush).

Run from this task's directory:

    uv run python tests/validate.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    load_ground_truth,
    measure_peak_memory,
    not_passed,
    passed,
    pg_conn,
    run_async,
)
from harness.service import run_app  # noqa: E402
from src.app import app  # noqa: E402

SMALL_CATEGORY_ID = 60  # smallest leaf category (673 products at SCALE=1.0) -- a genuinely small export
PRICE_TOLERANCE_SMALL = 0.01
PRICE_TOLERANCE_FULL = 1.0  # a ~26M-dollar sum over 200k rows; a slightly wider absolute tolerance, still tiny relative
MAX_PEAK_RATIO = 8.0  # full/small peak-memory ratio ceiling; row-count ratio here is ~300x


def _small_oracle():
    """Independent oracle for the small export: count, id checksum, price sum
    for SMALL_CATEGORY_ID, computed directly against shop.products."""
    with pg_conn() as conn:
        row = conn.execute(
            "SELECT count(*)::bigint, COALESCE(sum(id), 0)::bigint, "
            "COALESCE(sum(price), 0)::double precision "
            "FROM shop.products WHERE category_id = %s",
            (SMALL_CATEGORY_ID,),
        ).fetchone()
    return {"count": int(row[0]), "id_checksum": int(row[1]), "price_sum": float(row[2])}


async def _drain(category_id):
    """Launch the app fresh, GET /export/products (optionally filtered),
    and consume the NDJSON body incrementally -- only ever holding running
    scalar totals, never the collected rows, so the validator's own client
    code doesn't become the memory hog it's trying to detect in the app."""
    params = {"category_id": category_id} if category_id is not None else {}
    async with run_app(app) as svc:
        async with svc.client(timeout=120.0) as http:
            async with http.stream("GET", "/export/products", params=params) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    lines = body.decode(errors="replace").strip().splitlines()
                    tail = lines[-1] if lines else "(empty)"
                    not_passed(
                        f"GET /export/products?category_id={category_id} returned "
                        f"HTTP {r.status_code} (handler not implemented?): {tail[:200]}"
                    )
                ctype = r.headers.get("content-type", "")
                if "ndjson" not in ctype:
                    not_passed(
                        f"GET /export/products content-type {ctype!r} does not look like NDJSON "
                        f"(expected something containing 'ndjson', e.g. application/x-ndjson)"
                    )

                count = 0
                checksum = 0
                price_sum = 0.0
                last_id = None
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as e:
                        not_passed(f"export line is not valid JSON: {e} -- line started with {line[:80]!r}")
                    for key in ("id", "seller_id", "category_id", "title", "price", "in_stock", "created_at"):
                        if key not in obj:
                            not_passed(f"export row missing key {key!r}: {obj!r}")
                    rid = obj["id"]
                    if last_id is not None and rid <= last_id:
                        not_passed(f"export rows not strictly increasing by id ({last_id} -> {rid})")
                    last_id = rid
                    count += 1
                    checksum += int(rid)
                    price_sum += float(obj["price"])
    return count, checksum, price_sum


def _measure(category_id):
    (count, checksum, price_sum), peak = measure_peak_memory(lambda: run_async(_drain(category_id)))
    return count, checksum, price_sum, peak


@guarded
def main():
    small_oracle = _small_oracle()
    if small_oracle["count"] == 0:
        not_passed(f"category {SMALL_CATEGORY_ID} unexpectedly has 0 products in shop -- authoring bug, pick another")

    # Small export first: cheap, and fails fast on a stub/broken handler
    # before we ever pay for the full 200k-row sweep below.
    s_count, s_checksum, s_price_sum, s_peak = _measure(SMALL_CATEGORY_ID)

    if s_count != small_oracle["count"]:
        not_passed(
            f"category {SMALL_CATEGORY_ID} export returned {s_count} rows, "
            f"oracle (shop.products) says {small_oracle['count']}"
        )
    if s_checksum != small_oracle["id_checksum"]:
        not_passed(
            f"category {SMALL_CATEGORY_ID} export id checksum {s_checksum} != "
            f"oracle {small_oracle['id_checksum']} -- rows missing, duplicated, or wrong filter"
        )
    if abs(s_price_sum - small_oracle["price_sum"]) > PRICE_TOLERANCE_SMALL * max(1, s_count):
        not_passed(
            f"category {SMALL_CATEGORY_ID} export price sum {s_price_sum:.2f} != "
            f"oracle {small_oracle['price_sum']:.2f}"
        )

    # Full catalog export: the committed ground truth is the oracle, no live
    # query needed.
    gt = load_ground_truth()
    f_count, f_checksum, f_price_sum, f_peak = _measure(None)

    if f_count != gt["row_counts"]["products"]:
        not_passed(f"full export returned {f_count} rows, ground truth says {gt['row_counts']['products']}")
    if f_checksum != gt["products_id_checksum"]:
        not_passed(
            f"full export id checksum {f_checksum} != ground truth {gt['products_id_checksum']} -- "
            f"rows missing, duplicated, or out of the full catalog"
        )
    if abs(f_price_sum - gt["products_price_sum"]) > PRICE_TOLERANCE_FULL:
        not_passed(f"full export price sum {f_price_sum:.2f} != ground truth {gt['products_price_sum']:.2f}")

    # The point of the task: peak memory must stay near-flat as the export
    # grows, not scale with the row count (~300x more rows here).
    ratio = f_peak / s_peak if s_peak > 0 else float("inf")
    if ratio > MAX_PEAK_RATIO:
        not_passed(
            f"peak memory grew {ratio:.1f}x going from a {s_count}-row export to a {f_count}-row "
            f"export (row-count ratio ~{f_count / s_count:.0f}x) -- expected it to stay near-flat "
            f"(ratio <= {MAX_PEAK_RATIO:.0f}x); looks like the result is being materialized "
            f"(fetchall() / a full in-memory body) before or instead of actually streaming"
        )

    passed(
        f"{s_count}-row and {f_count}-row exports both correct vs the shop oracle "
        f"(count + id checksum + price sum); peak memory ratio {ratio:.2f}x across a "
        f"~{f_count / s_count:.0f}x row-count increase (threshold {MAX_PEAK_RATIO:.0f}x)"
    )


if __name__ == "__main__":
    main()
