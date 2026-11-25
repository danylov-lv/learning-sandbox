"""Measure shallow-vs-deep latency for BOTH pagination strategies on THIS
machine and write the result to a gitignored `pagination-local.json` via
`harness.common.write_baseline`.

The claim this task is built around -- "offset pagination gets linearly
worse with depth, cursor pagination stays flat" -- is a RELATIVE claim.
`tests/validate.py` asserts a ratio computed from this file, never a
hardcoded millisecond number. This script captures that ratio for the
machine it runs on.

Run this AFTER implementing `src/app.py`, then verify:

    uv run python baseline.py
    uv run python tests/validate.py

The app is launched in-process on an ephemeral port via `harness.service.
run_app` (a real socket, since this is a timing measurement, not a
correctness check). Each cycle times one shallow and one deep request for
each of the two strategies.
"""

import statistics
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import run_async, write_baseline  # noqa: E402
from harness.service import run_app  # noqa: E402
from src.app import app  # noqa: E402

LIMIT = 20
DEEP_POSITION = 190000  # deep into the 200,000-row catalog
N_CYCLES = 20


async def _bench():
    offset_shallow_ms = []
    offset_deep_ms = []
    cursor_shallow_ms = []
    cursor_deep_ms = []

    async with run_app(app) as svc:
        async with svc.client(timeout=30.0) as http:
            # Warm up connections/pool so the first timed request doesn't
            # eat one-time setup cost.
            await http.get(f"/products/offset?limit={LIMIT}&offset=0")
            await http.get(f"/products/offset?limit={LIMIT}&offset={DEEP_POSITION}")
            await http.get(f"/products/cursor?limit={LIMIT}")
            await http.get(f"/products/cursor?limit={LIMIT}&cursor={DEEP_POSITION}")

            for _ in range(N_CYCLES):
                t0 = time.perf_counter()
                r = await http.get(f"/products/offset?limit={LIMIT}&offset=0")
                offset_shallow_ms.append((time.perf_counter() - t0) * 1000.0)
                r.raise_for_status()

                t0 = time.perf_counter()
                r = await http.get(f"/products/offset?limit={LIMIT}&offset={DEEP_POSITION}")
                offset_deep_ms.append((time.perf_counter() - t0) * 1000.0)
                r.raise_for_status()

                t0 = time.perf_counter()
                r = await http.get(f"/products/cursor?limit={LIMIT}")
                cursor_shallow_ms.append((time.perf_counter() - t0) * 1000.0)
                r.raise_for_status()

                t0 = time.perf_counter()
                r = await http.get(f"/products/cursor?limit={LIMIT}&cursor={DEEP_POSITION}")
                cursor_deep_ms.append((time.perf_counter() - t0) * 1000.0)
                r.raise_for_status()

    return offset_shallow_ms, offset_deep_ms, cursor_shallow_ms, cursor_deep_ms


def main():
    offset_shallow_ms, offset_deep_ms, cursor_shallow_ms, cursor_deep_ms = run_async(_bench())

    offset_shallow = statistics.median(offset_shallow_ms)
    offset_deep = statistics.median(offset_deep_ms)
    cursor_shallow = statistics.median(cursor_shallow_ms)
    cursor_deep = statistics.median(cursor_deep_ms)

    offset_ratio = offset_deep / offset_shallow if offset_shallow > 0 else float("inf")
    cursor_ratio = cursor_deep / cursor_shallow if cursor_shallow > 0 else float("inf")

    print(
        f"offset: shallow median {offset_shallow:.3f} ms, deep median {offset_deep:.3f} ms, "
        f"ratio {offset_ratio:.2f}x"
    )
    print(
        f"cursor: shallow median {cursor_shallow:.3f} ms, deep median {cursor_deep:.3f} ms, "
        f"ratio {cursor_ratio:.2f}x"
    )

    result = {
        "limit": LIMIT,
        "deep_position": DEEP_POSITION,
        "n_cycles": N_CYCLES,
        "offset_shallow_ms": offset_shallow,
        "offset_deep_ms": offset_deep,
        "cursor_shallow_ms": cursor_shallow,
        "cursor_deep_ms": cursor_deep,
        "offset_ratio": offset_ratio,
        "cursor_ratio": cursor_ratio,
    }
    # write_baseline resolves relative paths against MODULE_ROOT, so namespace
    # the filename with the task dir to avoid collisions with other tasks.
    path = write_baseline("01-pagination-offset-vs-cursor/pagination-local.json", result)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
