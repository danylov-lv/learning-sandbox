"""Validator for 11-python-concurrency task 05 -- semaphore-rate-limiting.

Runs the learner's `fetch_all` against a mock peer configured with BOTH a
concurrency ceiling and a rate ceiling, and checks five properties, all
observed via `peer.stats` and the returned results -- no client-side
wall-clock assertions (the peer itself is the enforcer, see
`harness/peer.py`):

  1. No throttling: `peer.stats.throttled == 0`, i.e. `fetch_all` never
     exceeded either ceiling. This is the key check -- see the note below on
     why it genuinely requires both a semaphore AND a separate rate limiter.
  2. Concurrency cap respected: `peer.stats.max_observed_concurrency <=
     max_concurrency`.
  3. Concurrency was actually used (no cheating by going fully serial):
     `peer.stats.max_observed_concurrency >= min(max_concurrency, 2)`.
  4. Every path was fetched, with the correct body.
  5. No leaked asyncio tasks.

Why check 1 requires both controls, not just a semaphore: the peer here
allows 8 simultaneous requests (`max_concurrency`) but only 20 request
*starts* per second (`rate_per_sec`), while each request takes about 0.05s
(`base_latency`). A semaphore sized to 8 keeps the pipeline saturated at 8
in flight at all times -- as soon as one request finishes (~0.05s later),
the semaphore admits the next one immediately. Steady-state that's about
`8 / 0.05 = 160` request starts per second: eight times over the 20/sec
ceiling. A semaphore-only implementation will trip `throttled > 0` well
before finishing, even though it never once exceeded 8 in flight. Passing
this check requires a second, genuinely time-based mechanism gating request
*starts*, independent of the concurrency gate.

Run from this task's directory:

    uv run python tests/validate.py

Note on where the leak snapshot is taken: `before = snapshot_tasks()` is
taken BEFORE entering `async with mock_peer(...)`, and `leaked_tasks(before)`
is checked AFTER that block exits (peer fully torn down), not while the peer
is still running. mock_peer's own listen socket keeps an internal "waiting
for the next connection" task alive for as long as the server is up (on
Windows' ProactorEventLoop this task's identity churns -- a fresh Task each
time a connection is accepted), which is legitimate peer-internal
bookkeeping, not something fetch_all() created or is responsible for
cleaning up. Checking the diff only across the peer's full lifetime (started
and fully shut down inside the measured window) is what isolates "did the
LEARNER'S code leak a task" from "does the mock peer's own accept loop still
have a live task at the exact instant we happened to check" -- see
09-capstone-async-scraper/tests/validate_cp1.py for the same pattern.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, leaked_tasks, not_passed, passed, run_async, snapshot_tasks  # noqa: E402
from harness.peer import mock_peer  # noqa: E402
from src.fetcher import fetch_all  # noqa: E402

N_PATHS = 60
MAX_CONCURRENCY = 8
RATE_PER_SEC = 20
BASE_LATENCY = 0.05
SEED = 11205

PATHS = [f"/p/{i}" for i in range(1, N_PATHS + 1)]
CORPUS = {p: f"body-for-{p}".encode() for p in PATHS}


@guarded
def main():
    async def _run():
        before = snapshot_tasks()
        async with mock_peer(
            base_latency=BASE_LATENCY,
            max_concurrency=MAX_CONCURRENCY,
            rate_per_sec=RATE_PER_SEC,
            seed=SEED,
            corpus=CORPUS,
        ) as peer:
            results = await fetch_all(
                peer.base_url,
                PATHS,
                max_concurrency=MAX_CONCURRENCY,
                rate_per_sec=RATE_PER_SEC,
            )
            stats = peer.stats
        leaked = leaked_tasks(before)
        return stats, results, leaked

    stats, results, leaked = run_async(_run())

    # --- 5. No leaked tasks ----------------------------------------------
    if leaked:
        not_passed(f"leaked asyncio tasks after fetch_all returned: {leaked}")

    # --- 1. No throttling --------------------------------------------------
    if stats.throttled != 0:
        not_passed(
            f"peer rejected {stats.throttled} request(s) with 429 -- fetch_all exceeded "
            f"max_concurrency={MAX_CONCURRENCY} or rate_per_sec={RATE_PER_SEC} at some "
            "point. A semaphore alone bounds concurrency, not the rate of new request "
            "starts -- you need a separate time-based limiter too."
        )

    if not isinstance(results, dict):
        not_passed(f"fetch_all must return a dict[path, bytes], got {type(results).__name__}")

    # --- 4. All fetched, correct bodies (also catches silently-stored errors) -
    missing = [p for p in PATHS if p not in results]
    if missing:
        not_passed(f"{len(missing)} path(s) missing from the result, e.g. {missing[0]}")

    extra = [p for p in results if p not in CORPUS]
    if extra:
        not_passed(f"result contains {len(extra)} unexpected path(s), e.g. {extra[0]}")

    mismatched = [p for p in PATHS if results[p] != CORPUS[p]]
    if mismatched:
        not_passed(
            f"{len(mismatched)} path(s) returned an unexpected body (e.g. {mismatched[0]!r}: "
            f"got {results[mismatched[0]]!r}, expected {CORPUS[mismatched[0]]!r}) -- did an "
            "error response get stored instead of the real body?"
        )

    # --- 2. Concurrency cap respected --------------------------------------
    if stats.max_observed_concurrency > MAX_CONCURRENCY:
        not_passed(
            f"peer observed {stats.max_observed_concurrency} simultaneous in-flight requests, "
            f"exceeding max_concurrency={MAX_CONCURRENCY}"
        )

    # --- 3. Concurrency was actually used, not serialized -------------------
    min_expected = min(MAX_CONCURRENCY, 2)
    if stats.max_observed_concurrency < min_expected:
        not_passed(
            f"peer never observed more than {stats.max_observed_concurrency} simultaneous "
            f"in-flight request(s) -- expected at least {min_expected}. fetch_all appears to "
            "be running requests serially instead of using max_concurrency."
        )

    passed(
        f"fetched all {N_PATHS} paths, throttled={stats.throttled}, "
        f"max_observed_concurrency={stats.max_observed_concurrency}"
    )


if __name__ == "__main__":
    main()
