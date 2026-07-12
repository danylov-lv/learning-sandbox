"""Validator for 11-python-concurrency task 04 -- backpressure-bounded-queue.

Checks THREE properties of the learner's src/pipeline.py `run_pipeline`,
matching the README's "Completion criteria" exactly:

  1. Correctness on a large `produce_n`: every item 0..produce_n-1 is
     consumed exactly once (`consumed == produce_n`, `checksum ==
     sum(range(produce_n))`).
  2. Bounded memory: peak TRACED allocation (`measure_peak_memory`, i.e.
     tracemalloc peak, never RSS) for `produce_n = N` vs `produce_n = 4*N`,
     same small `max_in_flight` both times. A properly bounded pipeline's
     peak stays roughly flat (~1x-2x) because at most `max_in_flight`
     16KiB payloads are ever resident at once; an unbounded buffer's peak
     tracks total items produced, so it would show ~4x. The consumer sleeps
     briefly so it is the slow half of the pipeline -- otherwise the
     producer would never actually fill the buffer and the check would be
     meaningless.
  3. No leaked asyncio.Task after any run (`leaked_tasks(before) == []`).

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

from harness.common import guarded, leaked_tasks, measure_peak_memory, not_passed, passed, run_async, snapshot_tasks  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

# --- Check 1: correctness on a large produce_n ------------------------------
CORRECT_N = 10_000
CORRECT_MAX_IN_FLIGHT = 32

# --- Check 2: bounded memory, N vs 4N ---------------------------------------
# MEM_N is kept small deliberately: asyncio.sleep() on some platforms (e.g.
# Windows' default ~15ms timer resolution) rounds up any short sleep to that
# granularity, so a "tiny" per-item sleep can dominate wall time at a few
# hundred items. A few dozen items is plenty -- the 16KiB payloads dominate
# tracemalloc's traced peak over bookkeeping noise regardless of N's size,
# so the ratio signal is just as clean at N=64 as at N=500.
MEM_N = 64
MEM_MAX_IN_FLIGHT = 8
MEM_CONSUME_SLEEP = 0.001  # consumer is the slow half -- forces the buffer to fill
RATIO_THRESHOLD = 2.2  # "roughly flat" bounded vs ~4x for an unbounded buffer


async def _consume_noop(item):
    return None


async def _consume_slow(item):
    await asyncio.sleep(MEM_CONSUME_SLEEP)
    return None


def _check_result(result, produce_n, context):
    if not isinstance(result, dict):
        not_passed(f"{context}: run_pipeline must return a dict, got {type(result).__name__}")
    consumed = result.get("consumed")
    checksum = result.get("checksum")
    if consumed != produce_n:
        not_passed(f"{context}: expected consumed == {produce_n}, got {consumed!r}")
    expected_checksum = sum(range(produce_n))
    if checksum != expected_checksum:
        not_passed(f"{context}: expected checksum == {expected_checksum}, got {checksum!r}")


async def _check_correctness():
    before = snapshot_tasks()
    result = await run_pipeline(CORRECT_N, _consume_noop, CORRECT_MAX_IN_FLIGHT)
    _check_result(result, CORRECT_N, "correctness check")

    leaked = leaked_tasks(before)
    if leaked:
        not_passed(f"tasks leaked after a successful run_pipeline: {leaked}")

    return result["consumed"], result["checksum"]


async def _run_for_memory(produce_n):
    """Runs INSIDE the asyncio.run() that measure_peak_memory drives, so the
    leak check happens on the same loop as the code under test (leaked_tasks
    needs a running loop, and measure_peak_memory's asyncio.run has already
    torn the loop down by the time it returns to the caller)."""
    before = snapshot_tasks()
    result = await run_pipeline(produce_n, _consume_slow, MEM_MAX_IN_FLIGHT)
    leaked = leaked_tasks(before)
    return result, leaked


def _measure(produce_n):
    (result, leaked), peak_bytes = measure_peak_memory(_run_for_memory, produce_n)
    _check_result(result, produce_n, f"memory check (produce_n={produce_n})")

    if leaked:
        not_passed(f"tasks leaked after run_pipeline (produce_n={produce_n}): {leaked}")

    return peak_bytes


@guarded
def main():
    consumed, checksum = run_async(_check_correctness())

    peak_n = _measure(MEM_N)
    peak_4n = _measure(4 * MEM_N)

    if peak_n <= 0:
        not_passed(f"measured peak memory for produce_n={MEM_N} was {peak_n} bytes -- measurement failed")

    ratio = peak_4n / peak_n
    if ratio > RATIO_THRESHOLD:
        not_passed(
            f"peak memory grew {ratio:.2f}x going from produce_n={MEM_N} "
            f"(peak={peak_n} bytes) to produce_n={4 * MEM_N} (peak={peak_4n} bytes) "
            f"-- expected at most ~{RATIO_THRESHOLD}x for a properly bounded pipeline "
            f"(an unbounded buffer would show ~4x, tracking produce_n growth)"
        )

    passed(
        f"consumed={consumed}, checksum={checksum}; "
        f"peak memory N={MEM_N} -> {peak_n}B, 4N={4 * MEM_N} -> {peak_4n}B, ratio={ratio:.2f}x; "
        f"no leaked tasks"
    )


if __name__ == "__main__":
    main()
