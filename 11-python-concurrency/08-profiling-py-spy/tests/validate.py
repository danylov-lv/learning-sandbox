"""Validator for 11-python-concurrency task 08 -- profiling-py-spy.

py-spy attaches to a REAL running process -- there is no harness mock for
that, and this validator never shells out to py-spy itself (attaching to a
foreign process on Windows can require an elevated shell, which isn't
something a CI-portable validator can assume). Instead it gates on two
objective, script-checkable conditions:

  1. BEHAVIORAL: drive `src/app.py`'s importable `run_workload()` in-process,
     concurrently with a heartbeat coroutine, and check that the event loop
     stayed responsive -- same tick-deficit reasoning as task 01's validator
     (see its module docstring for the full argument). On the shipped,
     unfixed app, `compute_signature` runs inline on the event-loop thread
     and this fails. After the learner offloads it (or makes it cheap
     enough not to matter), it passes.
  2. WRITEUP: `ANSWER.md` must be filled in -- names the function the
     learner found via py-spy, is not a stub, and demonstrates they
     actually used py-spy (a handful of grounding keywords) rather than
     guessing from the source.

Run from this task's directory:

    uv run python tests/validate.py
"""

import re
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, leaked_tasks, not_passed, passed, run_async, snapshot_tasks  # noqa: E402
from src.app import run_workload  # noqa: E402

# CONCURRENCY is deliberately low. A correctly-offloaded compute_signature
# still contends for the GIL against every other worker thread doing the
# same CPU-bound work; at higher concurrency (e.g. 8) that contention alone
# drags a *fixed* run's heartbeat fraction down to where it's no longer
# reliably distinguishable from a broken run's. At concurrency=1 the two
# states separate cleanly and consistently (~0.42 broken vs. ~0.64 fixed,
# empirically stable across repeated runs) without relying on a large
# worker pool to prove the point -- the property under test is "does this
# block the loop thread," not "is this pipeline fast under load."
N_VALIDATE = 40
CONCURRENCY = 1
FETCH_LATENCY = 0.005
PERSIST_LATENCY = 0.005
HEARTBEAT_INTERVAL = 0.01

ANSWER_PATH = TASK_ROOT / "ANSWER.md"
PLACEHOLDER_MARKER = "(answer here)"
MIN_PROSE_CHARS = 200
ACCEPTED_CULPRIT_SUBSTRINGS = ["compute_signature", "compute signature"]
GROUNDING_KEYWORDS = [
    "py-spy", "pyspy", "flamegraph", "flame graph", "event loop",
    "gil", "to_thread", "run_in_executor", "thread pool", "blocking", "dump",
]
MIN_GROUNDING_KEYWORDS = 3


def _drive_workload():
    import asyncio

    async def _check():
        before = snapshot_tasks()

        ticks = 0

        async def _heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                ticks += 1

        hb_task = asyncio.create_task(_heartbeat())
        start = time.perf_counter()
        try:
            stats = await run_workload(
                n_records=N_VALIDATE,
                concurrency=CONCURRENCY,
                fetch_latency=FETCH_LATENCY,
                persist_latency=PERSIST_LATENCY,
            )
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
        elapsed = time.perf_counter() - start

        leaked = leaked_tasks(before)
        return stats, ticks, elapsed, leaked

    return run_async(_check())


def _check_answer():
    if not ANSWER_PATH.exists():
        not_passed(f"ANSWER.md not found at {ANSWER_PATH}")

    text = ANSWER_PATH.read_text(encoding="utf-8")
    lower = text.lower()

    if PLACEHOLDER_MARKER in lower:
        not_passed("ANSWER.md still has unfilled '(answer here)' placeholder(s)")

    prose = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    prose = "\n".join(ln for ln in prose.splitlines() if not ln.strip().startswith("#"))
    prose_len = len(prose.strip())
    if prose_len < MIN_PROSE_CHARS:
        not_passed(
            f"ANSWER.md has only {prose_len} character(s) of prose (need at least "
            f"{MIN_PROSE_CHARS}) -- write a real answer, not a stub"
        )

    if not any(s in lower for s in ACCEPTED_CULPRIT_SUBSTRINGS):
        not_passed(
            "ANSWER.md doesn't name the hot function you found with py-spy "
            f"(expected it to mention one of {ACCEPTED_CULPRIT_SUBSTRINGS!r})"
        )

    hits = sorted(kw for kw in GROUNDING_KEYWORDS if kw in lower)
    if len(hits) < MIN_GROUNDING_KEYWORDS:
        not_passed(
            f"ANSWER.md only touches {len(hits)} profiling concept(s) ({hits}); need at "
            f"least {MIN_GROUNDING_KEYWORDS} of {GROUNDING_KEYWORDS} to show you actually "
            "used py-spy rather than guessing"
        )


@guarded
def main():
    stats, ticks, elapsed, leaked = _drive_workload()

    # --- 1. Correctness (guards against a "fix" that skips the work) ------
    if not isinstance(stats, dict) or stats.get("records_processed") != N_VALIDATE:
        not_passed(
            f"run_workload(n_records={N_VALIDATE}) reported "
            f"records_processed={stats.get('records_processed') if isinstance(stats, dict) else stats!r} "
            f"-- expected exactly {N_VALIDATE}"
        )
    if stats.get("errors", 0):
        not_passed(f"run_workload reported {stats['errors']} error(s) processing synthetic records")

    # --- 2. No leaked tasks -------------------------------------------------
    if leaked:
        not_passed(f"{len(leaked)} task(s) leaked (created but never awaited/cancelled): {leaked}")

    # --- 3. Loop not starved -------------------------------------------------
    # Same reasoning as task 01: an unblocked loop ticks roughly
    # elapsed/HEARTBEAT_INTERVAL times. compute_signature's CPU-bound loop,
    # called inline on the event-loop thread once per record, burns a real,
    # calibrated stretch of wall-clock time with zero yield points each
    # call -- asyncio.sleep can't "catch up" on ticks lost during that
    # stretch. Offloading it (to_thread/executor) keeps the loop thread free
    # to service the heartbeat's timer throughout, so ticks track elapsed
    # closely.
    expected_unblocked_ticks = elapsed / HEARTBEAT_INTERVAL
    min_ticks = max(10, int(expected_unblocked_ticks * 0.5))
    if ticks < min_ticks:
        not_passed(
            f"event loop stalled while run_workload() processed {N_VALIDATE} records: "
            f"heartbeat ticked {ticks} time(s) in {elapsed:.3f}s (expected at least "
            f"{min_ticks}, ~{expected_unblocked_ticks:.0f} if the loop were never blocked) "
            "-- something in the pipeline is running CPU-bound work directly on the "
            "event-loop thread; profile the live process with py-spy to find it"
        )

    # --- 4. Writeup -----------------------------------------------------------
    _check_answer()

    passed(
        f"{N_VALIDATE} records processed; heartbeat ticks={ticks} in {elapsed:.3f}s; "
        "ANSWER.md OK"
    )


if __name__ == "__main__":
    main()
