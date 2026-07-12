"""Validator for 11-python-concurrency task 03 -- cancellation-and-timeouts.

Checks THREE independent properties of the learner's src/timeouts.py
`guarded_operation()`, all robust to machine speed -- every sleep/timeout
value below is small and fixed, chosen only so the intended outcome (a
timeout fires, a cancellation lands mid-work) is guaranteed regardless of
how fast or slow the runner is, never compared against wall-clock duration:

  1. Timeout releases the resource: work() outlives timeout ->
     guarded_operation() raises TimeoutError, the resource pool's `in_use`
     count returns to its starting value (no leak), and no asyncio Task is
     left behind.
  2. External cancellation propagates, not swallowed: guarded_operation()
     is started as a Task and cancelled mid-work; awaiting that Task must
     raise CancelledError (not return normally, not raise something else)
     AND the resource must still have been released.
  3. A shielded finalizer runs to completion despite a timeout: a
     finalizer that flips a flag after a short sleep must have flipped
     that flag by the time guarded_operation()'s TimeoutError has
     propagated back here, proving the finalizer was awaited to completion
     rather than cut short or merely fired-and-forgotten.

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

from harness.common import (  # noqa: E402
    guarded,
    leaked_tasks,
    not_passed,
    passed,
    run_async,
    snapshot_tasks,
)
from src.timeouts import guarded_operation  # noqa: E402

TIMEOUT = 0.1
SLOW_WORK = 1.0  # comfortably longer than TIMEOUT -- guaranteed to trip it
FINALIZER_SLEEP = 0.05  # shorter than SLOW_WORK, long enough to prove it ran
CANCEL_DELAY = 0.05  # give guarded_operation time to acquire + enter work()


class ResourcePool:
    """Minimal resource pool for the validator: tracks how many resources
    are currently checked out. Starts at 0 -- a correct guarded_operation()
    must always return this to 0 by the time its call has finished, no
    matter which of the three ways below it finished."""

    def __init__(self):
        self.in_use = 0

    async def acquire(self):
        self.in_use += 1
        return object()

    def release(self, handle):
        self.in_use -= 1


async def _sleeper(seconds):
    await asyncio.sleep(seconds)


async def _check_timeout_releases_resource():
    pool = ResourcePool()
    before = snapshot_tasks()

    try:
        await guarded_operation(pool, lambda: _sleeper(SLOW_WORK), timeout=TIMEOUT)
    except TimeoutError:
        pass
    except asyncio.CancelledError:
        not_passed(
            "guarded_operation() raised CancelledError for a plain timeout -- "
            "expected TimeoutError"
        )
    else:
        not_passed(
            f"guarded_operation() returned normally even though work() sleeps "
            f"{SLOW_WORK}s against a {TIMEOUT}s timeout"
        )

    if pool.in_use != 0:
        not_passed(
            f"resource leaked on timeout: pool.in_use == {pool.in_use}, expected 0 "
            "(release() was skipped on the timeout path)"
        )

    leaked = leaked_tasks(before)
    if leaked:
        not_passed(f"timeout path left {len(leaked)} task(s) behind: {leaked}")


async def _check_cancellation_propagates():
    pool = ResourcePool()
    before = snapshot_tasks()

    task = asyncio.create_task(
        guarded_operation(pool, lambda: _sleeper(SLOW_WORK), timeout=10.0)
    )
    await asyncio.sleep(CANCEL_DELAY)  # let it acquire the resource and enter work()
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        not_passed(
            "cancelling guarded_operation() did not raise CancelledError back to "
            "the caller -- cancellation was swallowed"
        )

    if pool.in_use != 0:
        not_passed(
            f"resource leaked on external cancellation: pool.in_use == {pool.in_use}, "
            "expected 0"
        )

    leaked = leaked_tasks(before)
    if leaked:
        not_passed(f"cancellation path left {len(leaked)} task(s) behind: {leaked}")


async def _check_shielded_finalizer_completes():
    pool = ResourcePool()
    state = {"finalized": False}

    async def finalizer():
        await asyncio.sleep(FINALIZER_SLEEP)
        state["finalized"] = True

    try:
        await guarded_operation(
            pool, lambda: _sleeper(SLOW_WORK), timeout=TIMEOUT, finalizer=finalizer
        )
    except TimeoutError:
        pass
    else:
        not_passed("expected TimeoutError from guarded_operation() with a finalizer set")

    if not state["finalized"]:
        not_passed(
            "finalizer did not run to completion despite the timeout -- it was cut "
            "short (or never awaited) instead of shielded to completion"
        )

    if pool.in_use != 0:
        not_passed(
            f"resource leaked on timeout with a finalizer set: pool.in_use == "
            f"{pool.in_use}, expected 0"
        )


@guarded
def main():
    async def _run_all():
        await _check_timeout_releases_resource()
        await _check_cancellation_propagates()
        await _check_shielded_finalizer_completes()

    run_async(_run_all())
    passed(
        "timeout releases the resource, external cancellation propagates, "
        "shielded finalizer completes -- no leaks in any path"
    )


if __name__ == "__main__":
    main()
