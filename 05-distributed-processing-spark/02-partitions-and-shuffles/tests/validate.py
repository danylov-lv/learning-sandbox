"""Validator for 02-partitions-and-shuffles.

Needs a live SparkSession, so it runs inside the container:
    ./run.sh 02-partitions-and-shuffles/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    RAW_EVENTS_DIR,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_learner_module,
    load_results,
    passed,
    plan_has,
)

RESULTS_PATH = TASK_ROOT / "results-local.json"

# salted skew ratio must beat naive by at least this fraction (structural, not absolute)
SKEW_IMPROVEMENT_FACTOR = 0.75


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()

    mod = load_learner_module(TASK_ROOT / "src" / "partitions.py", "partitions")
    for fn in ("repartition_vs_coalesce", "shuffle_partitions_effect", "skew_partition_counts"):
        if not hasattr(mod, fn):
            fail(f"src/partitions.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("02-partitions-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        # --- repartition_vs_coalesce ---
        rc = mod.repartition_vs_coalesce(spark, RAW_EVENTS_DIR, 8, 2)
        for key in (
            "source_partitions",
            "repartition_partitions",
            "repartition_plan",
            "coalesce_partitions",
            "coalesce_plan",
        ):
            if key not in rc:
                fail(f"repartition_vs_coalesce result missing key '{key}'")

        if rc["repartition_partitions"] != 8:
            fail(f"repartition_partitions={rc['repartition_partitions']}, expected 8 (the requested target)")
        if rc["coalesce_partitions"] != 2:
            fail(f"coalesce_partitions={rc['coalesce_partitions']}, expected 2 (the requested target)")
        if not plan_has(rc["repartition_plan"], "Exchange"):
            fail("repartition_plan does not contain 'Exchange' — repartition() should always shuffle")
        if plan_has(rc["coalesce_plan"], "Exchange"):
            fail("coalesce_plan contains 'Exchange' — coalesce() reducing partition count should not shuffle")

        # --- shuffle_partitions_effect ---
        configured = [4, 17]
        eff = mod.shuffle_partitions_effect(spark, RAW_EVENTS_DIR, configured)
        if not isinstance(eff, dict):
            fail(f"shuffle_partitions_effect must return a dict, got {type(eff).__name__}")
        for v in configured:
            if str(v) not in eff:
                fail(f"shuffle_partitions_effect result missing key '{v}'")
            if eff[str(v)] != v:
                fail(f"shuffle.partitions={v} produced a result with {eff[str(v)]} partitions, expected {v}")
        if eff[str(configured[0])] == eff[str(configured[1])]:
            fail("shuffle_partitions_effect produced the same partition count for two different configured values")

        # --- skew_partition_counts ---
        n_salts = 8
        n_partitions = 20
        skew = mod.skew_partition_counts(spark, RAW_EVENTS_DIR, n_salts, n_partitions)
        for key in ("naive_partition_row_counts", "salted_partition_row_counts", "rows_by_source_after_dedup"):
            if key not in skew:
                fail(f"skew_partition_counts result missing key '{key}'")

        naive_counts = skew["naive_partition_row_counts"]
        salted_counts = skew["salted_partition_row_counts"]
        if not naive_counts or not salted_counts:
            fail("naive_partition_row_counts / salted_partition_row_counts must be non-empty")

        def skew_ratio(counts):
            counts = [c for c in counts if c is not None]
            mean = sum(counts) / len(counts)
            if mean == 0:
                fail("mean partition row count is 0 — no rows landed anywhere")
            return max(counts) / mean

        naive_ratio = skew_ratio(naive_counts)
        salted_ratio = skew_ratio(salted_counts)

        if naive_ratio <= 1.5:
            fail(
                f"naive skew ratio ({naive_ratio:.2f}) is too flat to be a meaningful baseline — "
                "expected the naive per-source partitioning to show real skew on this dataset"
            )
        if salted_ratio > naive_ratio * SKEW_IMPROVEMENT_FACTOR:
            fail(
                f"salted skew ratio ({salted_ratio:.2f}) is not meaningfully better than "
                f"naive ({naive_ratio:.2f}) — expected salted/naive <= {SKEW_IMPROVEMENT_FACTOR}, "
                f"got {salted_ratio / naive_ratio:.2f}"
            )

        rows_by_source = skew["rows_by_source_after_dedup"]
        expected_rbs = gt["rows_by_source"]
        if set(rows_by_source.keys()) != set(expected_rbs.keys()):
            fail(
                f"rows_by_source_after_dedup keys {sorted(rows_by_source.keys())} != "
                f"ground-truth keys {sorted(expected_rbs.keys())}"
            )
        for k in expected_rbs:
            if int(rows_by_source[k]) != int(expected_rbs[k]):
                fail(f"rows_by_source_after_dedup[{k}]={rows_by_source[k]}, expected {expected_rbs[k]}")

    finally:
        spark.stop()

    results = load_results(RESULTS_PATH, what="results-local.json")
    for key in ("naive_seconds", "salted_seconds"):
        if key not in results:
            fail(f"results-local.json missing '{key}' — run tests/bench.py first")

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"repartition/coalesce, shuffle.partitions effect, and skew salting all check out "
        f"(naive_ratio={naive_ratio:.2f}, salted_ratio={salted_ratio:.2f})"
    )


if __name__ == "__main__":
    main()
