"""Validator for 09-olap-clickhouse-duckdb task 07 -- duckdb-vs-clickhouse.

Checks THREE things about the learner's src/bench.py:

  1. Correctness (a hard gate) -- both ch_answer() and duck_answer() must
     reproduce data/ground-truth.json's per_category_instock: every
     category's count exact, avg_price within a rounding tolerance, and the
     category SET matching exactly (no missing/extra categories from either
     engine).
  2. Agreement (a hard gate, and the actual point of this task) -- ch_answer()
     and duck_answer() must agree WITH EACH OTHER within the same tolerance.
     Both read the same underlying data (observations_raw and the Parquet
     lake are coherent copies); if they disagree, something is broken
     regardless of what ground truth says.
  3. Timing (informational) -- both functions are timed with
     harness.common.time_it, the baseline is refreshed via write_baseline,
     and ch_seconds / duck_seconds / the ratio are printed. This is NOT an
     assertion: at the small scale used for local verification the two
     engines can land close together, which is itself part of the lesson
     (see README) -- the real gap opens up at 50M rows, not 500k.

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
    duckdb_connect,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    time_it,
    write_baseline,
)
from src.bench import ch_answer, duck_answer  # noqa: E402

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


def _check_agreement(ch_result, duck_result):
    ch_categories = set(ch_result)
    duck_categories = set(duck_result)
    if ch_categories != duck_categories:
        missing = duck_categories - ch_categories
        extra = ch_categories - duck_categories
        not_passed(
            f"ch_answer() and duck_answer() disagree on the category set -- "
            f"missing from ch {sorted(missing)}, extra in ch {sorted(extra)}"
        )

    for cat in ch_categories:
        ch_count, ch_avg = ch_result[cat]
        duck_count, duck_avg = duck_result[cat]
        if int(ch_count) != int(duck_count):
            not_passed(
                f"engines disagree for category={cat!r}: ch count={ch_count}, "
                f"duck count={duck_count} -- same underlying data should give an "
                "exact count match"
            )
        if abs(float(ch_avg) - float(duck_avg)) > AVG_TOLERANCE:
            not_passed(
                f"engines disagree for category={cat!r}: ch avg={ch_avg}, "
                f"duck avg={duck_avg}, expected agreement within {AVG_TOLERANCE}"
            )


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["per_category_instock"]

    client = ch_client()
    con = duckdb_connect()
    try:
        # 1. Correctness -- the hard gate. Time while we're at it so a wrong
        #    answer doesn't cost us a second, separately-timed run.
        ch_result, ch_seconds = time_it(ch_answer, client)
        _check_result("ch_answer", ch_result, expected)

        duck_result, duck_seconds = time_it(duck_answer, con)
        _check_result("duck_answer", duck_result, expected)

        # 2. Agreement -- the other hard gate, and the actual point: same
        #    data, same answer, different engine.
        _check_agreement(ch_result, duck_result)

        # 3. Timing -- informational only (see module docstring / README).
        ratio = ch_seconds / duck_seconds if duck_seconds > 0 else float("inf")
        write_baseline(
            BASELINE_PATH, {"ch_seconds": ch_seconds, "duck_seconds": duck_seconds, "ratio": ratio}
        )
        print(f"ch_seconds:   {ch_seconds:.4f}")
        print(f"duck_seconds: {duck_seconds:.4f}")
        print(f"ratio (ch_seconds / duck_seconds): {ratio:.2f}x")

        passed(
            f"both engines matched ground truth and each other for {len(expected)} "
            f"categories (ch={ch_seconds:.4f}s, duck={duck_seconds:.4f}s, ratio={ratio:.2f}x)"
        )
    finally:
        client.close()
        con.close()


if __name__ == "__main__":
    main()
