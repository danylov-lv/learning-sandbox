"""Validator for 06-parquet-to-minio-s3a.

Needs a live SparkSession with s3a wired up, so it runs inside the container:
    ./run.sh 06-parquet-to-minio-s3a/tests/validate.py

This validator never writes to the lake itself. It only reads whatever the
learner's own job (run separately via ./run.sh, see the README) left at the
fixed path s3a://price-lake-05/task-06/lake.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    S3_BUCKET,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_learner_module,
    passed,
    plan_has,
)

LAKE_DEST = f"s3a://{S3_BUCKET}/task-06/lake"

# Fixed so the pruning gate is reproducible across dataset scales — every
# generated dataset spans 2025-01..2026-06, so this key always exists.
PROBE_MONTH = "2025-09"


@guarded
def main():
    gt = load_ground_truth()
    expected_rows_by_month = gt["rows_by_month"]
    expected_total = gt["distinct_rows"]

    mod = load_learner_module(TASK_ROOT / "src" / "lake.py", "lake")
    for fn in ("write_month_partitioned", "inspect_lake_files", "pruned_read"):
        if not hasattr(mod, fn):
            fail(f"src/lake.py has no {fn}(...) function")

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.errors import AnalysisException

    spark = SparkSession.builder.appName("06-parquet-to-minio-s3a-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.adaptive.enabled", "false")

    try:
        try:
            lake_df = spark.read.parquet(LAKE_DEST)
        except (AnalysisException, Exception) as e:
            msg = str(e)
            if "Path does not exist" in msg or "does not exist" in msg or "NoSuchBucket" in msg or "404" in msg:
                fail(
                    f"no lake found at {LAKE_DEST} — run your write job first, e.g. add a "
                    "__main__ block to src/lake.py that calls write_month_partitioned(spark, "
                    f'RAW_EVENTS_DIR, "{LAKE_DEST}") and run it via ./run.sh (see the README)'
                )
            raise

        if "month" not in lake_df.columns:
            fail(f"lake at {LAKE_DEST} has no 'month' column — expected a partitionBy('month') layout")

        # --- rows_by_month, exactly, all months ---
        counts = {
            row["month"]: row["cnt"]
            for row in lake_df.groupBy("month").agg(F.count(F.lit(1)).alias("cnt")).collect()
        }
        total = sum(counts.values())

        missing_months = sorted(set(expected_rows_by_month) - set(counts))
        extra_months = sorted(set(counts) - set(expected_rows_by_month))
        if missing_months:
            fail(f"lake is missing month partition(s): {missing_months}")
        if extra_months:
            fail(f"lake has unexpected month partition(s) not in ground truth: {extra_months}")

        mismatches = {
            m: (counts[m], expected_rows_by_month[m])
            for m in expected_rows_by_month
            if counts[m] != expected_rows_by_month[m]
        }
        if mismatches:
            sample = dict(list(mismatches.items())[:5])
            fail(f"per-month row counts do not match ground truth for {len(mismatches)} month(s), e.g. {sample}")

        if total != expected_total:
            fail(f"total rows in lake = {total}, expected ground-truth distinct_rows = {expected_total}")

        # --- layout: month= dirs, one file per partition ---
        layout = mod.inspect_lake_files(spark, LAKE_DEST)
        if not isinstance(layout, dict) or "files_per_month" not in layout or "all_paths_have_month_dir" not in layout:
            fail("inspect_lake_files must return {'files_per_month': dict, 'all_paths_have_month_dir': bool}")

        if layout["all_paths_have_month_dir"] is not True:
            fail("inspect_lake_files reports paths without a 'month=' directory segment")

        files_per_month = layout["files_per_month"]
        bad_counts = {m: n for m, n in files_per_month.items() if n != 1}
        if bad_counts:
            sample = dict(list(bad_counts.items())[:5])
            fail(
                f"expected exactly 1 file per month partition, found otherwise for "
                f"{len(bad_counts)} month(s), e.g. {sample} — repartition by the partition "
                "column before writing (see write_month_partitioned's docstring)"
            )
        if set(files_per_month) != set(expected_rows_by_month):
            fail("inspect_lake_files' files_per_month keys do not cover all 18 expected months")

        # --- pruning ---
        pruned = mod.pruned_read(spark, LAKE_DEST, PROBE_MONTH)
        if not isinstance(pruned, dict) or not {"plan", "row_count", "distinct_files_touched"} <= pruned.keys():
            fail("pruned_read must return {'plan': str, 'row_count': int, 'distinct_files_touched': int}")

        plan = pruned["plan"]
        if not plan_has(plan, r"PartitionFilters:\s*\[[^\]]*month[^\]]*\]"):
            fail(
                "pruned_read's plan has no non-empty PartitionFilters mentioning 'month' on the "
                "scan node — expected the s3a Parquet scan to prune by partition, not just filter rows after reading"
            )
        if plan_has(plan, r"PartitionFilters:\s*\[\]"):
            fail("pruned_read's plan has an empty PartitionFilters list — the month filter was not pushed to the scan")

        if pruned["row_count"] != expected_rows_by_month[PROBE_MONTH]:
            fail(
                f"pruned_read row_count={pruned['row_count']} for month={PROBE_MONTH}, "
                f"expected {expected_rows_by_month[PROBE_MONTH]} (ground-truth rows_by_month)"
            )
        if pruned["distinct_files_touched"] != 1:
            fail(
                f"pruned_read touched {pruned['distinct_files_touched']} distinct file(s) for a "
                "single-month filter, expected exactly 1 — a correctly pruned, correctly written "
                "read should only open that month's one file"
            )

    finally:
        spark.stop()

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(f"lake row counts match ground truth for all 18 months, layout is 1 file/partition, and month={PROBE_MONTH} read pruned to a single file")


if __name__ == "__main__":
    main()
