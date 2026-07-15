"""Measure THIS machine's stock (unfixed) throughput for
`GET /catalog/{category_id}` and write it to a gitignored
`catalog-load-local.json` via `harness.common.write_baseline`.

The claim this task is built around -- "the stock app's throughput collapses
under concurrency; a correct application-layer fix recovers most of it" -- is
a RELATIVE claim. `tests/validate.py` asserts a ratio computed from this
file, never a hardcoded RPS/ms number (timing is never absolute, per this
module's design). This script captures that ratio's stock side, on this
machine, for the STOCK src/app.py exactly as shipped.

Run this BEFORE touching src/app.py, then again is harmless (it always
re-measures whatever src/app.py currently does):

    uv run python baseline.py
    # ... then implement your fix in src/app.py ...
    uv run python tests/validate.py

The app is launched as a REAL SUBPROCESS via `harness.service.
run_app_subprocess` -- not in-process. What this task is hunting lives at
the OS/event-loop scheduling level, not just in the SQL that runs; running
the app in-process inside this script's own event loop would let
cooperative scheduling between "the load" and "the app" paper over exactly
that, since they'd share one thread instead of being two independent
processes talking over a real socket.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import run_async, write_baseline  # noqa: E402
from harness.load import bombard  # noqa: E402
from harness.service import run_app_subprocess  # noqa: E402

# Fixed load shape -- validate.py bombards the SAME way, so the two RPS
# numbers are comparable. Category 9 ("Headphones & Audio") is the largest
# leaf category (52,169 products at SCALE=1.0), so every page here is a full
# page regardless of offset.
CATEGORY_ID = 9
LIMIT = 30
OFFSET = 0
CONCURRENCY = 30
WARMUP_REQUESTS = 10
DURATION_S = 6.0

PATH = f"/catalog/{CATEGORY_ID}?limit={LIMIT}&offset={OFFSET}"


async def _bench():
    async with run_app_subprocess(
        "src.app:app", env={"PYTHONPATH": str(TASK_ROOT)}
    ) as svc:
        url = svc.base_url + PATH
        # Warm up: first-connection setup (pool open, TCP handshake reuse)
        # shouldn't be counted as part of the timed run.
        await bombard(url, concurrency=1, requests=WARMUP_REQUESTS)
        result = await bombard(url, concurrency=CONCURRENCY, duration_s=DURATION_S)
    return result


def main():
    result = run_async(_bench())

    print(
        f"stock: {result.total} requests in {result.elapsed_s:.2f}s "
        f"({result.ok} ok, {result.errors} errors) -> "
        f"{result.rps:.1f} rps, p50 {result.p50_ms:.1f} ms, "
        f"p95 {result.p95_ms:.1f} ms, p99 {result.p99_ms:.1f} ms"
    )
    if result.errors:
        print(
            f"WARNING: {result.errors} of {result.total} requests errored -- "
            f"is the stock app even reachable/correct? baseline includes them as failures."
        )

    payload = {
        "category_id": CATEGORY_ID,
        "limit": LIMIT,
        "offset": OFFSET,
        "concurrency": CONCURRENCY,
        "duration_s": DURATION_S,
        "rps": result.rps,
        "p50_ms": result.p50_ms,
        "p95_ms": result.p95_ms,
        "p99_ms": result.p99_ms,
        "total": result.total,
        "ok": result.ok,
        "errors": result.errors,
    }
    # write_baseline resolves relative paths against MODULE_ROOT, so
    # namespace the filename with the task dir to avoid collisions.
    path = write_baseline("09-load-test-and-bottleneck-hunt/catalog-load-local.json", payload)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
