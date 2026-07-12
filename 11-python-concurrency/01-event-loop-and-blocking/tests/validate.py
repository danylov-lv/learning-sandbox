"""Validator for 11-python-concurrency task 01 -- event-loop-and-blocking.

Checks FOUR properties of the learner's src/fetcher.py, all structural /
behavioral (no absolute wall-clock pass/fail thresholds -- see below for how
the loop-starvation check stays machine-independent):

  1. Correctness: fetch_all() returns blocking_parse(body) for every path,
     keyed correctly, compared against the validator computing the same
     thing independently from the corpus it handed the peer.
  2. Concurrency achieved: the peer observed multiple simultaneously
     in-flight requests. A `for` loop that awaits one request before
     starting the next pins max_observed_concurrency at 1 -- this check
     alone defeats that failure mode.
  3. Loop not starved: a heartbeat coroutine ticks (await asyncio.sleep(H))
     concurrently with fetch_all(). blocking_parse here is a BLOCKING call
     that releases the GIL while it runs (`time.sleep` stands in for
     blocking I/O or a native/C-extension parser) -- offloading pure-Python
     CPU work to a thread would NOT free the loop (the GIL stays held), so
     this task deliberately uses a GIL-releasing blocking cost instead: that
     is the only shape where "offloaded" and "inline" produce a measurably
     different heartbeat rate. This check first CALIBRATES the achievable
     solo heartbeat rate on THIS machine (mirrors
     07-sync-async-bridging/tests/validate.py), then compares the observed
     ticks during fetch_all() against that calibrated rate rather than a
     theoretical 1/H constant -- see the comment above the check for the
     exact reasoning and margins.
  4. No leaked tasks: whatever concurrency primitive was used, nothing is
     left behind un-awaited. The snapshot is taken BEFORE the mock peer is
     started and the leak diff is computed AFTER it has fully shut down, so
     the peer's own internal accept-loop task (which churns identity on
     Windows/Proactor as connections are accepted) is never mistaken for a
     leak left behind by fetch_all() -- see the note above _check().

Run from this task's directory:

    uv run python tests/validate.py
"""

import asyncio
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, leaked_tasks, not_passed, passed, run_async, snapshot_tasks  # noqa: E402
from harness.peer import mock_peer  # noqa: E402
from src.fetcher import fetch_all  # noqa: E402

N_PATHS = 24
BASE_LATENCY = 0.12
HEARTBEAT_INTERVAL = 0.01
CALIBRATE_DURATION = 0.3

# GIL-releasing blocking cost per parsed body. A pure-Python CPU-bound stand-in
# would NOT discriminate offloaded-vs-inline (the GIL stays held either way),
# so blocking_parse blocks via time.sleep -- releasing the GIL for the
# duration, same as blocking I/O or a native/C-extension parser would.
BLOCK_SECONDS = 0.006

# Minimum simultaneously in-flight requests the peer must observe. A serial
# (one-await-at-a-time) fetcher pins max_observed_concurrency at 1, so any
# threshold above 1 defeats it; min(N_PATHS, 6) also caps the requirement
# sensibly if a task author ever shrinks N_PATHS.
MIN_CONCURRENCY = min(N_PATHS, 6)

# Empirically (see .authoring/): a correctly offloaded implementation
# (asyncio.gather + await asyncio.to_thread(blocking_parse, body)) achieves a
# tick fraction of ~1.0 relative to the calibrated solo rate; an inline
# implementation (blocking_parse(body) called directly on the loop thread)
# achieves ~0.53. 0.75 sits with wide headroom above the inline number and
# wide headroom below the offloaded number, and is machine-independent
# because both the numerator (ticks) and the denominator (elapsed *
# solo_rate) are measured on this run/this machine, not assumed.
MIN_TICK_FRACTION = 0.75


def blocking_parse(body: bytes) -> object:
    """A synchronous, genuinely BLOCKING "parse" -- a tiny deterministic hash
    over the first 32 bytes (so the validator can compute the expected result
    independently) followed by a GIL-releasing blocking wait standing in for
    blocking I/O or a native/C-extension parser. No `await` inside it, no
    cooperative yield point -- calling it on the event loop thread blocks
    that thread for BLOCK_SECONDS."""
    x = 0
    for b in body[:32]:
        x = (x * 31 + b) & 0xFFFFFFFF
    time.sleep(BLOCK_SECONDS)
    return {"checksum": x, "len": len(body)}


def _build_corpus():
    paths = [f"/item/{i}" for i in range(N_PATHS)]
    corpus = {p: f"body-for-{p}-{'x' * 40}".encode() for p in paths}
    return paths, corpus


async def _calibrate_heartbeat_rate():
    """Measure how many heartbeat ticks/second this machine actually achieves
    with NOTHING else running, at HEARTBEAT_INTERVAL. Naively assuming
    1/HEARTBEAT_INTERVAL ticks/second overstates what real OS timer/event-loop
    resolution delivers (Windows' ~64Hz timer floor, in particular), which
    would make check 3 either falsely fail a correct offloaded implementation
    or, worse, pass a subtly broken one. Calibrating first makes the later
    comparison relative to what THIS machine can actually do."""
    ticks = 0

    async def _heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            ticks += 1

    hb_task = asyncio.create_task(_heartbeat())
    start = time.perf_counter()
    await asyncio.sleep(CALIBRATE_DURATION)
    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass
    elapsed = time.perf_counter() - start
    return ticks / elapsed if elapsed > 0 else 0.0


# Note on where the leak snapshot is taken: `before = snapshot_tasks()` is
# taken BEFORE entering `async with mock_peer(...)`, and `leaked_tasks(before)`
# is checked AFTER that block exits (peer fully torn down), not while the
# peer is still running. mock_peer's own listen socket keeps an internal
# "waiting for the next connection" task alive for as long as the server is
# up (on Windows' ProactorEventLoop this task's identity churns -- a fresh
# Task each time a connection is accepted), which is legitimate peer-internal
# bookkeeping, not something fetch_all() created or is responsible for
# cleaning up. Checking the diff only across the peer's full lifetime (started
# and fully shut down inside the measured window) is what isolates "did the
# LEARNER'S code leak a task" from "does the mock peer's own accept loop
# still have a live task at the exact instant we happened to check" -- see
# 09-capstone-async-scraper/tests/validate_cp1.py for the same pattern.
async def _check(paths, corpus):
    before = snapshot_tasks()
    async with mock_peer(base_latency=BASE_LATENCY, corpus=corpus) as peer:
        ticks = 0

        async def _heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                ticks += 1

        hb_task = asyncio.create_task(_heartbeat())
        start = time.perf_counter()
        try:
            result = await fetch_all(peer.base_url, paths, blocking_parse)
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
        elapsed = time.perf_counter() - start
        stats = peer.stats
    leaked = leaked_tasks(before)
    return result, stats, ticks, elapsed, leaked


@guarded
def main():
    paths, corpus = _build_corpus()
    expected = {p: blocking_parse(corpus[p]) for p in paths}

    solo_rate = run_async(_calibrate_heartbeat_rate())
    result, stats, ticks, elapsed, leaked = run_async(_check(paths, corpus))

    # --- 1. Correctness ---------------------------------------------------
    if not isinstance(result, dict):
        not_passed(f"fetch_all must return a dict, got {type(result).__name__}")

    missing = [p for p in paths if p not in result]
    if missing:
        not_passed(f"missing {len(missing)} path(s) in result, e.g. {missing[:3]!r}")

    extra = [p for p in result if p not in expected]
    if extra:
        not_passed(f"result contains {len(extra)} unexpected path(s), e.g. {extra[:3]!r}")

    wrong = [p for p in paths if result.get(p) != expected[p]]
    if wrong:
        not_passed(
            f"{len(wrong)} path(s) parsed incorrectly, e.g. {wrong[0]!r}: "
            f"got {result.get(wrong[0])!r}, expected {expected[wrong[0]]!r}"
        )

    # --- 2. Concurrency achieved -------------------------------------------
    if stats.max_observed_concurrency < MIN_CONCURRENCY:
        not_passed(
            f"peer observed at most {stats.max_observed_concurrency} simultaneously "
            f"in-flight request(s) out of {N_PATHS} paths -- expected at least "
            f"{MIN_CONCURRENCY}; requests are being awaited one at a time instead of "
            "concurrently"
        )

    # --- 3. Loop not starved -------------------------------------------------
    # frac = observed ticks / (elapsed * this-machine's calibrated solo rate).
    # An offloaded implementation keeps the loop thread free to service the
    # heartbeat's timer throughout fetch_all(), so ticks track the calibrated
    # solo rate closely (frac ~1.0). An implementation that calls
    # blocking_parse inline burns BLOCK_SECONDS-sized stretches of the loop's
    # only thread with zero yield points, N_PATHS times; asyncio.sleep cannot
    # "catch up" missed wakeups once the thread is free again, so those
    # stretches are a dead loss of ticks (frac ~0.53 measured). MIN_TICK_
    # FRACTION=0.75 sits with wide headroom on both sides of that gap -- see
    # the module docstring and the constant's comment above for the numbers.
    frac = ticks / (elapsed * solo_rate) if solo_rate > 0 else 0.0
    if frac < MIN_TICK_FRACTION:
        not_passed(
            f"heartbeat achieved only {frac:.2f}x the calibrated solo tick rate "
            f"({ticks} ticks in {elapsed:.3f}s vs a calibrated {solo_rate:.1f} ticks/s, "
            f"expected at least {MIN_TICK_FRACTION:.2f}x) -- blocking_parse is likely "
            "being called directly on the event loop thread instead of offloaded"
        )

    # --- 4. No leaked tasks ---------------------------------------------------
    if leaked:
        not_passed(f"{len(leaked)} task(s) leaked (created but never awaited/cancelled): {leaked}")

    passed(
        f"{N_PATHS} paths fetched correctly; max_observed_concurrency="
        f"{stats.max_observed_concurrency}; heartbeat frac={frac:.2f} "
        f"({ticks} ticks in {elapsed:.3f}s)"
    )


if __name__ == "__main__":
    main()
