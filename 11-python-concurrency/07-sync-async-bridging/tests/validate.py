"""Validator for 11-python-concurrency task 07 -- sync-async-bridging.

Checks FOUR behavioral properties of the learner's src/bridge.py, all
machine-speed independent (no absolute wall-clock pass/fail thresholds):

  1. Loop responsiveness: a cheap heartbeat coroutine ticks (await
     asyncio.sleep(H)) concurrently with process_batch() over a batch whose
     blocking_lib genuinely blocks its calling OS thread (time.sleep, not
     asyncio.sleep). An implementation that calls blocking_lib inline on the
     event loop thread collapses ticks to ~0 for the whole batch (nothing
     else can run while the loop thread is stuck inside time.sleep); a
     correctly offloaded implementation keeps the loop thread free the whole
     time, so ticks track a solo, nothing-else-running heartbeat closely.
     The achievable tick rate at a given H is itself OS/timer-resolution
     dependent (observed well below the naive 1/H on some platforms), so
     this check first CALIBRATES the achievable solo rate on THIS machine,
     then compares the batch's observed ticks against that measured rate
     rather than a theoretical constant -- see the tick-deficit reasoning
     comment below (mirrors 01-event-loop-and-blocking/tests/validate.py,
     adapted to calibrate instead of assuming 1/H).
  2. Bounded concurrency: blocking_lib records the maximum number of
     simultaneous in-flight calls (via a lock-protected counter, since
     offloaded calls run on real worker threads). Asserts this never exceeds
     max_workers AND, with enough items, actually reaches it -- the cap must
     be used, not serialized down to one call at a time.
  3. Input order: results[i] corresponds to items[i] even though items are
     given deliberately mismatched durations, so completion order visibly
     differs from input order unless process_batch preserves order on
     purpose.
  4. Sync entrypoint: sync_entrypoint() is called from plain synchronous
     code (no event loop running on this thread) and must return the
     correct list, having actually driven process_batch to completion.

Run from this task's directory:

    uv run python tests/validate.py
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, run_async  # noqa: E402
from src.bridge import process_batch, sync_entrypoint  # noqa: E402

HEARTBEAT_INTERVAL = 0.005
CALIBRATE_DURATION = 0.25

RESP_ITEMS = 16
RESP_DURATION = 0.06
RESP_MAX_WORKERS = 4

BOUND_ITEMS = 16
BOUND_DURATION = 0.05
BOUND_MAX_WORKERS = 4

ORDER_DURATIONS = [0.12, 0.01, 0.09, 0.02, 0.15, 0.03]

SYNC_ITEMS = 5
SYNC_DURATION = 0.02
SYNC_MAX_WORKERS = 2


class BlockingLib:
    """Synchronous, genuinely-blocking stand-in for a third-party call.

    Each item is a `(duration_seconds, value)` pair; the call sleeps
    `duration_seconds` via `time.sleep` -- a real OS-thread block, never
    `asyncio.sleep` -- then returns `value`. A lock-protected counter tracks
    how many calls are simultaneously in flight, so a validator running on
    the SAME instance across many concurrent offloaded calls can read back
    `max_in_flight` afterward.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def __call__(self, item):
        duration, value = item
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        time.sleep(duration)
        with self._lock:
            self._in_flight -= 1
        return value


async def _calibrate_heartbeat_rate():
    """Measure how many heartbeat ticks/second this machine actually achieves
    with NOTHING else running, at HEARTBEAT_INTERVAL. Naively assuming
    1/HEARTBEAT_INTERVAL ticks/second overstates what real OS timer/event-loop
    resolution delivers (observed well under half of that on some platforms),
    which would make the deficit check below either falsely fail a correct
    offloaded implementation or (worse) pass a subtly-broken one. Calibrating
    first makes the later comparison relative to what THIS machine can
    actually do, not a theoretical constant."""
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


async def _check_loop_responsiveness(baseline_rate):
    lib = BlockingLib()
    items = [(RESP_DURATION, i) for i in range(RESP_ITEMS)]

    ticks = 0

    async def _heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            ticks += 1

    hb_task = asyncio.create_task(_heartbeat())
    start = time.perf_counter()
    try:
        results = await process_batch(items, lib, RESP_MAX_WORKERS)
    finally:
        hb_task.cancel()
        try:
            await hb_task
        except asyncio.CancelledError:
            pass
    elapsed = time.perf_counter() - start

    expected = list(range(RESP_ITEMS))
    if results != expected:
        not_passed(f"process_batch returned {results}, expected {expected}")

    # Calling blocking_lib inline burns RESP_DURATION-sized stretches of real
    # OS-thread time on the loop's only thread with zero yield points;
    # asyncio.sleep cannot "catch up" missed wakeups once the thread is free
    # again, so every such stretch is a dead loss of ticks that never gets
    # recovered, while elapsed still grows by that same stretch -- a fully
    # inline batch measures ~0 ticks here regardless of RESP_ITEMS *
    # RESP_DURATION. An offloaded (to_thread / executor) implementation keeps
    # the loop thread free to service the heartbeat's timer throughout, so
    # ticks track what the calibration step measured as achievable, scaled to
    # this run's elapsed time. min_ticks sits well below that calibrated
    # expectation (comfortable margin for scheduling noise) but far above the
    # ~0 an inline implementation leaves standing.
    expected_ticks = baseline_rate * elapsed
    min_ticks = max(5, int(expected_ticks * 0.4))
    if ticks < min_ticks:
        not_passed(
            f"heartbeat ticked only {ticks} time(s) in {elapsed:.3f}s while "
            f"process_batch() ran (expected at least {min_ticks}, ~"
            f"{expected_ticks:.0f} based on this machine's calibrated solo "
            "heartbeat rate) -- blocking_lib is likely being called inline on "
            "the event loop thread instead of offloaded to a worker thread"
        )

    return ticks, elapsed


async def _check_bounded_concurrency():
    lib = BlockingLib()
    items = [(BOUND_DURATION, i) for i in range(BOUND_ITEMS)]

    results = await process_batch(items, lib, BOUND_MAX_WORKERS)

    expected = list(range(BOUND_ITEMS))
    if results != expected:
        not_passed(f"process_batch returned {results}, expected {expected}")

    if lib.max_in_flight > BOUND_MAX_WORKERS:
        not_passed(
            f"observed {lib.max_in_flight} simultaneous blocking_lib call(s), "
            f"more than max_workers={BOUND_MAX_WORKERS} -- offload concurrency "
            "is not bounded"
        )
    if lib.max_in_flight < BOUND_MAX_WORKERS:
        not_passed(
            f"observed at most {lib.max_in_flight} simultaneous blocking_lib "
            f"call(s) with {BOUND_ITEMS} items in flight, expected the cap of "
            f"{BOUND_MAX_WORKERS} to actually be reached -- offload concurrency "
            "appears serialized rather than using the full worker budget"
        )

    return lib.max_in_flight


async def _check_input_order():
    lib = BlockingLib()
    items = [(d, f"item-{i}") for i, d in enumerate(ORDER_DURATIONS)]

    # max_workers == len(items): every item can run concurrently, so
    # completion order is driven purely by duration and visibly differs from
    # input order unless process_batch deliberately preserves it.
    results = await process_batch(items, lib, len(items))

    expected = [f"item-{i}" for i in range(len(ORDER_DURATIONS))]
    if results != expected:
        not_passed(
            f"process_batch returned {results}, which does not match input "
            f"order {expected} -- results must follow items' order, not "
            "completion order"
        )

    return results


def _check_sync_entrypoint():
    lib = BlockingLib()
    items = [(SYNC_DURATION, i * 10) for i in range(SYNC_ITEMS)]

    results = sync_entrypoint(items, lib, SYNC_MAX_WORKERS)

    expected = [i * 10 for i in range(SYNC_ITEMS)]
    if results != expected:
        not_passed(f"sync_entrypoint returned {results}, expected {expected}")

    return results


@guarded
def main():
    baseline_rate = run_async(_calibrate_heartbeat_rate())
    ticks, elapsed = run_async(_check_loop_responsiveness(baseline_rate))
    max_in_flight = run_async(_check_bounded_concurrency())
    run_async(_check_input_order())
    _check_sync_entrypoint()

    passed(
        f"heartbeat ticks={ticks} in {elapsed:.3f}s; max simultaneous "
        f"blocking_lib calls={max_in_flight}; input order preserved; "
        "sync_entrypoint drove process_batch to completion correctly"
    )


if __name__ == "__main__":
    main()
