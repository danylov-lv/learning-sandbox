"""Checker for 12-worker-lock-queue.

Run from the module root:
    uv run python 12-worker-lock-queue/tests/check.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK_ROOT / "src"))

import psycopg  # noqa: E402

import harness  # noqa: E402

N_ROWS = 40_000
BATCH_SIZE = 200
N_WORKERS = 8
SLEEP_S = 0.02

# Stock (plain FOR UPDATE) measured ~1.0x -- all workers serialize on the
# same lock queue. A correct SKIP LOCKED claim measured ~6.3x on the same
# machine/arena. The bar is set well below the fixed number and well above
# what stock can reach, so it fails stock by a wide margin (see
# .authoring/tasks-w3b.md for the calibration numbers).
SCALING_FACTOR = 3.0

CLAIM_SQL_PATH = TASK_ROOT / "src" / "claim.sql"


def main():
    claim_sql = CLAIM_SQL_PATH.read_text(encoding="utf-8")

    print(f"single-worker reference drain ({N_ROWS} rows)...")
    harness.setup_arena(N_ROWS)
    try:
        ref = harness.drain(claim_sql, 1, BATCH_SIZE, SLEEP_S, monitor=False)
    except psycopg.Error as e:
        harness.teardown_arena()
        print(f"NOT PASSED: could not run single-worker reference drain: {e}")
        sys.exit(1)
    harness.teardown_arena()
    print(f"info  1-worker wall time: {ref['wall_s']:.2f}s")

    print(f"\n{N_WORKERS}-worker drain against current src/claim.sql ({N_ROWS} rows)...")
    harness.setup_arena(N_ROWS)
    try:
        multi = harness.drain(claim_sql, N_WORKERS, BATCH_SIZE, SLEEP_S)
        pending, claimed = harness.coverage_counts()
    except psycopg.Error as e:
        harness.teardown_arena()
        print(f"NOT PASSED: could not run {N_WORKERS}-worker drain: {e}")
        sys.exit(1)
    harness.teardown_arena()
    print(f"info  {N_WORKERS}-worker wall time: {multi['wall_s']:.2f}s")
    print(f"info  per-worker claimed counts: {multi['per_worker_counts']}")
    print(f"info  max observed lock-waiting sessions: {multi['max_lock_waiters']}")

    # Gate 1: correctness -- zero duplicate claims and full coverage.
    if multi["duplicate_count"] != 0:
        reason = (
            f"{multi['duplicate_count']} row(s) were claimed by more than one worker -- "
            "this is a race in the claim query, not a performance issue"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    print("PASS  zero duplicate claims")

    if pending != 0 or claimed != N_ROWS:
        reason = (
            f"arena not fully drained: {pending} still pending, {claimed} claimed "
            f"(expected 0 pending, {N_ROWS} claimed)"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    print(f"PASS  full coverage: all {N_ROWS} rows claimed exactly once")

    # Gate 2: throughput -- multi-worker drain must scale, not serialize.
    threshold_s = ref["wall_s"] / SCALING_FACTOR
    if multi["wall_s"] > threshold_s:
        reason = (
            f"{N_WORKERS}-worker wall time {multi['wall_s']:.2f}s > "
            f"{threshold_s:.2f}s (1-worker {ref['wall_s']:.2f}s / {SCALING_FACTOR}x) -- "
            "workers are not claiming in parallel, they are queuing on the same lock"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    speedup = ref["wall_s"] / multi["wall_s"] if multi["wall_s"] > 0 else float("inf")
    print(f"PASS  {N_WORKERS}-worker wall time {multi['wall_s']:.2f}s <= {threshold_s:.2f}s "
          f"(speedup {speedup:.2f}x)")

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
