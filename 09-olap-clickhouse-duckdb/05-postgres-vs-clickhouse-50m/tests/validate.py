"""Validator for 09-olap-clickhouse-duckdb task 05 -- postgres-vs-clickhouse-50m.

Checks TWO things about the learner's src/compare.py:

  1. Correctness (the hard gate) -- both pg_answer() and ch_answer() must
     reproduce data/ground-truth.json's per_category_instock: every
     category's count exact, avg_price within a rounding tolerance, and the
     category SET matching exactly (no missing/extra categories from either
     engine). A fast wrong answer fails.
  2. Timing (informational) -- both functions are timed with
     harness.common.time_it, the baseline is refreshed via write_baseline,
     and pg_seconds / ch_seconds / the ratio are printed. This is NOT an
     assertion: relative wall-clock timing at the small scale used for local
     verification is noisy (see README), so it is recorded, not gated on.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    ch_client,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
    time_it,
    write_baseline,
)
from src.compare import ch_answer, pg_answer  # noqa: E402

AVG_TOLERANCE = 0.01
BASELINE_PATH = TASK_ROOT / "baseline-local.json"


def _check_result(label, got, expected):
    if not isinstance(got, dict) or not got:
        not_passed(f"{label}() returned no usable result (expected a non-empty dict)")

    got_categories = set(got)
    expected_categories = set(expected)
    if got_categories != expected_categories:
        missing = expected_categories - got_categories
        extra = got_categories - expected_categories
        not_passed(
            f"{label}() category set mismatch -- missing {sorted(missing)}, "
            f"extra {sorted(extra)}"
        )

    for cat, exp in expected.items():
        exp_count, exp_avg = exp["count"], exp["avg"]
        try:
            count, avg = got[cat]
        except (TypeError, ValueError):
            not_passed(f"{label}()[{cat!r}] is not a (count, avg_price) pair: {got[cat]!r}")

        if int(count) != exp_count:
            not_passed(
                f"{label}(): category={cat!r} count={count}, expected {exp_count} exactly"
            )
        if abs(float(avg) - exp_avg) > AVG_TOLERANCE:
            not_passed(
                f"{label}(): category={cat!r} avg={avg}, expected {exp_avg} "
                f"within {AVG_TOLERANCE}"
            )


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["per_category_instock"]

    conn = pg_connect()
    client = ch_client()
    try:
        # 1. Correctness -- the hard gate. Time while we're at it so a wrong
        #    answer doesn't cost us a second, separately-timed run.
        pg_result, pg_seconds = time_it(pg_answer, conn)
        _check_result("pg_answer", pg_result, expected)

        ch_result, ch_seconds = time_it(ch_answer, client)
        _check_result("ch_answer", ch_result, expected)

        # 2. Timing -- informational only (see module docstring / README).
        ratio = pg_seconds / ch_seconds if ch_seconds > 0 else float("inf")
        write_baseline(
            BASELINE_PATH, {"pg_seconds": pg_seconds, "ch_seconds": ch_seconds, "ratio": ratio}
        )
        print(f"pg_seconds:  {pg_seconds:.4f}")
        print(f"ch_seconds:  {ch_seconds:.4f}")
        print(f"speedup (pg_seconds / ch_seconds): {ratio:.2f}x")

        passed(
            f"both engines matched ground truth for {len(expected)} categories "
            f"(pg={pg_seconds:.4f}s, ch={ch_seconds:.4f}s, ratio={ratio:.2f}x)"
        )
    finally:
        conn.close()
        client.close()


if __name__ == "__main__":
    main()
