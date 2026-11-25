"""Measure MISS vs HIT latency for the caching endpoint on THIS machine and
write the result to a gitignored `caching-local.json` via
`harness.common.write_baseline`.

The cache speedup is a RELATIVE claim: the validator asserts the HIT path is
materially faster than the MISS path on the machine it runs on, never a
hardcoded millisecond number. That ratio is what this script captures.

Run this AFTER implementing `src/app.py`, then verify:

    uv run python baseline.py
    uv run python tests/validate.py

The app is launched in-process on an ephemeral port via `harness.service.
run_app`; each cycle forces a MISS (invalidate first, then time one GET) and
then times a run of warm HITs against the same category.
"""

import statistics
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import redis_client, redis_flush_prefix, run_async, write_baseline  # noqa: E402
from harness.service import run_app  # noqa: E402
from src.app import CACHE_PREFIX, app  # noqa: E402

TASK_PREFIX = "s12:t02:"
CATEGORY_ID = 9  # the largest leaf (Headphones & Audio) -- a genuinely heavy MISS
N_MISS_CYCLES = 5
N_HITS_PER_CYCLE = 25


async def _bench():
    miss_ms = []
    hit_ms = []
    async with run_app(app) as svc:
        async with svc.client(timeout=30.0) as http:
            # Warm up the app's DB/redis connections so the first MISS timing
            # reflects the query, not one-time connection setup.
            await http.post(f"/categories/{CATEGORY_ID}/invalidate")
            await http.get(f"/categories/{CATEGORY_ID}/summary")

            for _ in range(N_MISS_CYCLES):
                await http.post(f"/categories/{CATEGORY_ID}/invalidate")
                t0 = time.perf_counter()
                r = await http.get(f"/categories/{CATEGORY_ID}/summary")
                miss_ms.append((time.perf_counter() - t0) * 1000.0)
                r.raise_for_status()
                if r.headers.get("X-Cache") != "MISS":
                    raise RuntimeError(f"expected X-Cache: MISS after invalidate, got {r.headers.get('X-Cache')!r}")

                for _ in range(N_HITS_PER_CYCLE):
                    t0 = time.perf_counter()
                    r = await http.get(f"/categories/{CATEGORY_ID}/summary")
                    hit_ms.append((time.perf_counter() - t0) * 1000.0)
                    r.raise_for_status()
                    if r.headers.get("X-Cache") != "HIT":
                        raise RuntimeError(f"expected X-Cache: HIT on a warm request, got {r.headers.get('X-Cache')!r}")

    return miss_ms, hit_ms


def main():
    client = redis_client()
    redis_flush_prefix(client, TASK_PREFIX)
    try:
        miss_ms, hit_ms = run_async(_bench())
    finally:
        redis_flush_prefix(client, TASK_PREFIX)

    miss = statistics.median(miss_ms)
    hit = statistics.median(hit_ms)
    ratio = miss / hit if hit > 0 else float("inf")

    print(f"category {CATEGORY_ID}: MISS median {miss:.3f} ms, HIT median {hit:.3f} ms, speedup {ratio:.1f}x")

    result = {
        "category_id": CATEGORY_ID,
        "miss_ms": miss,
        "hit_ms": hit,
        "speedup": ratio,
        "cache_prefix": CACHE_PREFIX,
        "n_miss": len(miss_ms),
        "n_hit": len(hit_ms),
    }
    # write_baseline resolves relative paths against MODULE_ROOT, so namespace
    # the filename with the task dir to avoid collisions with other tasks.
    path = write_baseline("02-response-caching-redis/caching-local.json", result)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
