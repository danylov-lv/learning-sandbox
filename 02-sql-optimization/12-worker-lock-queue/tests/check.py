"""Check claim correctness and throughput on a fresh arena for each run."""

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
SCALING_FACTOR = 3.0
CLAIM_SQL_PATH = TASK_ROOT / "src" / "claim.sql"


def run_arena(claim_sql, workers):
    try:
        harness.setup_arena(N_ROWS)
        expected_ids = harness.ids_with_status("pending")
        if len(expected_ids) != N_ROWS:
            raise harness.ClaimContractError(
                f"arena contains {len(expected_ids)} pending rows, expected {N_ROWS}"
            )

        stats = harness.drain(claim_sql, workers, BATCH_SIZE, SLEEP_S, monitor=workers > 1)
        claimed_ids = harness.ids_with_status("claimed")
        if stats["duplicate_count"]:
            raise harness.ClaimContractError(
                f"{stats['duplicate_count']} ID(s) were returned more than once"
            )
        if claimed_ids != expected_ids:
            raise harness.ClaimContractError(
                f"arena coverage differs from the original pending rows "
                f"({len(expected_ids - claimed_ids)} missing, {len(claimed_ids - expected_ids)} extra)"
            )

        returned_ids = stats["returned_ids"]
        if returned_ids != claimed_ids:
            raise harness.ClaimContractError(
                f"returned IDs differ from claimed rows "
                f"({len(claimed_ids - returned_ids)} missing, {len(returned_ids - claimed_ids)} extra)"
            )
        return stats
    finally:
        harness.teardown_arena()


def main():
    try:
        claim_sql = CLAIM_SQL_PATH.read_text(encoding="utf-8")
        print(f"single-worker reference drain ({N_ROWS} rows)...")
        ref = run_arena(claim_sql, 1)
        print(f"info  1-worker wall time: {ref['wall_s']:.2f}s")

        print(f"\n{N_WORKERS}-worker drain against current src/claim.sql ({N_ROWS} rows)...")
        multi = run_arena(claim_sql, N_WORKERS)
    except (OSError, psycopg.Error, harness.ClaimContractError) as e:
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    print(f"info  {N_WORKERS}-worker wall time: {multi['wall_s']:.2f}s")
    print(f"info  per-worker claimed counts: {multi['per_worker_counts']}")
    print(f"info  max observed lock-waiting sessions: {multi['max_lock_waiters']}")
    print(f"PASS  all {N_ROWS} rows were claimed and returned exactly once within the batch limit")

    threshold_s = ref["wall_s"] / SCALING_FACTOR
    if multi["wall_s"] > threshold_s:
        print(
            f"NOT PASSED: {N_WORKERS}-worker wall time {multi['wall_s']:.2f}s exceeds "
            f"{threshold_s:.2f}s (1-worker {ref['wall_s']:.2f}s / {SCALING_FACTOR}x)"
        )
        sys.exit(1)

    speedup = ref["wall_s"] / multi["wall_s"] if multi["wall_s"] > 0 else float("inf")
    print(f"PASS  {N_WORKERS}-worker drain is {speedup:.2f}x faster")
    print("PASSED")


if __name__ == "__main__":
    main()
