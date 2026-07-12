"""Validator for 11-python-concurrency task 02 -- taskgroup-structured-concurrency.

Checks TWO behavioral properties of the learner's src/fanout.py, both
machine-speed independent (no wall-clock throughput thresholds):

  1. Happy path: workers run concurrently (not serially), results come back
     correct AND in input order (not completion order -- workers are given
     deliberately mismatched durations so the two orders would visibly
     differ if run_fanout got this wrong), and no task is left alive
     afterward.
  2. Failure cancels siblings + propagates: one worker fails after a short
     delay; a "long" sibling worker would only flip a shared flag after a
     much longer sleep. run_fanout must raise (ExceptionGroup or the bare
     underlying exception, either is accepted -- see src/fanout.py
     guarantee 3), the long sibling's flag must never be set (proof it was
     cancelled mid-sleep, not left running to completion), and no task may
     be left alive afterward.

Run from this task's directory:

    uv run python tests/validate.py
"""

import asyncio
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, leaked_tasks, not_passed, passed, run_async, snapshot_tasks  # noqa: E402
from src.fanout import run_fanout  # noqa: E402

# --- Check 1: happy path ---------------------------------------------------
N_ITEMS = 6
SLEEP_SLOW = 0.15
SLEEP_FAST = 0.03

# --- Check 2: failure cancels siblings + propagates -------------------------
FAIL_DELAY = 0.05
LONG_DELAY = 0.3


class DeliberateFailure(Exception):
    """Raised by a worker on purpose, to be distinguished from bugs."""


async def _check_happy_path():
    before = snapshot_tasks()

    in_flight = {"current": 0, "max": 0}
    items = list(range(N_ITEMS))

    async def worker(item):
        in_flight["current"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["current"])
        # Alternate slow/fast so completion order differs from input order --
        # a real test of "results in input order", not just "results present".
        await asyncio.sleep(SLEEP_SLOW if item % 2 == 0 else SLEEP_FAST)
        in_flight["current"] -= 1
        return item * 2

    results = await run_fanout(items, worker)

    expected = [item * 2 for item in items]
    if results != expected:
        not_passed(f"expected results {expected} in input order, got {results}")

    min_expected_concurrency = min(N_ITEMS, 4)
    if in_flight["max"] < min_expected_concurrency:
        not_passed(
            f"max observed concurrency was {in_flight['max']}, expected at least "
            f"{min_expected_concurrency} -- workers do not appear to run concurrently"
        )

    leaked = leaked_tasks(before)
    if leaked:
        not_passed(f"tasks leaked after a successful run_fanout: {leaked}")

    return in_flight["max"]


async def _check_failure_propagation():
    before = snapshot_tasks()

    state = {"long_finished": False}
    items = ["normal-1", "fail", "normal-2", "long"]

    async def worker(item):
        if item == "fail":
            await asyncio.sleep(FAIL_DELAY)
            raise DeliberateFailure("deliberate worker failure")
        if item == "long":
            await asyncio.sleep(LONG_DELAY)
            state["long_finished"] = True
            return item
        await asyncio.sleep(FAIL_DELAY / 2)
        return item

    caught = None
    try:
        await run_fanout(items, worker)
    except BaseException as exc:  # noqa: BLE001 -- must catch cancellation-shaped exceptions too
        caught = exc

    if caught is None:
        not_passed("run_fanout did not raise when one worker failed -- the failure must propagate")

    is_direct = isinstance(caught, DeliberateFailure)
    is_grouped = isinstance(caught, BaseExceptionGroup) and any(
        isinstance(exc, DeliberateFailure) for exc in caught.exceptions
    )
    if not (is_direct or is_grouped):
        not_passed(
            "expected run_fanout to raise DeliberateFailure directly or a "
            f"BaseExceptionGroup containing it, got {caught!r}"
        )

    # Let cancellations settle before checking for leaks.
    await asyncio.sleep(0)

    leaked = leaked_tasks(before)
    if leaked:
        not_passed(f"tasks leaked after run_fanout raised: {leaked}")

    # Wait past the long sibling's sleep duration. If it was truly cancelled,
    # its flag-setting line never runs, no matter how long we wait. If it was
    # merely orphaned (leaked but not caught above), it finishes late and
    # flips the flag here.
    await asyncio.sleep(LONG_DELAY)

    if state["long_finished"]:
        not_passed(
            "the long-running sibling completed after a peer failed -- it should "
            "have been cancelled promptly, not left running to completion"
        )

    return caught


@guarded
def main():
    max_concurrency = run_async(_check_happy_path())
    caught = run_async(_check_failure_propagation())

    passed_kind = "BaseExceptionGroup" if isinstance(caught, BaseExceptionGroup) else type(caught).__name__
    passed(
        f"max observed concurrency {max_concurrency}; failure propagated as "
        f"{passed_kind}; long sibling cancelled; no leaked tasks"
    )


if __name__ == "__main__":
    main()
