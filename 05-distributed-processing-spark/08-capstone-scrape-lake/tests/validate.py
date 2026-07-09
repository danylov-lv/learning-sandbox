"""Validator for 08-capstone-scrape-lake.

Three checkpoints:

--cp1   Calls the learner's src/pipeline.py build_silver(...) directly (this
        IS the write job, not a separate read-only check — running this
        builds s3a://price-lake-05/capstone/silver). Then checks: per-month
        row counts match ground-truth.json's rows_by_month exactly (18/18);
        total matches distinct_rows; rows_by_region (derived independently,
        in pure Python, from rows_by_source + sources.csv's source_id ->
        region map) matches the lake's actual per-region counts;
        region/vertical/tier columns present; layout is month=<value>
        directories with a small, bounded file count per partition; the
        returned plan shows at least two BroadcastHashJoin occurrences and
        no SortMergeJoin.

--cp2   Calls the learner's src/tuned.py run_naive(...) and run_tuned(...)
        directly against the CP1 silver lake (fails cleanly if it isn't
        there yet). Checks: both DataFrames' collected results agree
        (region, sum_delta, avg_delta, n) within tolerance; the naive
        plan contains a SortMergeJoin; the tuned plan's "== Final Plan =="
        section (or the whole plan, if AQE produced no such section)
        contains a BroadcastHashJoin and no SortMergeJoin there; and
        results-local.json (written separately by tests/bench.py, not by
        this validator) shows tuned_seconds meaningfully below
        naive_seconds.

--cp3   NOTES.md and DESIGN.md both have real content (check_notes_filled,
        DESIGN.md held to a higher bar).

No flags: run all three in order, stop at the first failure.

Usage (from module root, always via the container -- CP1/CP2 need a live
SparkSession with s3a wired up):
    ./run.sh 08-capstone-scrape-lake/tests/validate.py [--cp1] [--cp2] [--cp3]
"""

import argparse
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TASK_ROOT = TESTS_DIR.parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    REFERENCE_DIR,
    RAW_EVENTS_DIR,
    S3_BUCKET,
    approx,
    check_notes_filled,
    load_ground_truth,
    load_learner_module,
    load_results,
    passed,
    plan_has,
)

SILVER_DEST = f"s3a://{S3_BUCKET}/capstone/silver"
NOTES_PATH = TASK_ROOT / "NOTES.md"
DESIGN_PATH = TASK_ROOT / "DESIGN.md"
RESULTS_PATH = TASK_ROOT / "results-local.json"

MAX_FILES_PER_MONTH = 8
# Empirically measured on the reference machine (2M-row committed dataset,
# local[*], MinIO in the same compose stack): naive ~1.1s, tuned ~0.4-0.5s
# via the noop sink, consistently a >2x gap across repeated runs. This
# margin (require tuned at most 90% of naive) is generous slack under
# that observed ratio -- see README/NOTES for the honesty caveat about
# local-mode timing noise at small scale.
MAX_TUNED_OVER_NAIVE_RATIO = 0.9


def _cp_fail(cp, reason):
    print(f"NOT PASSED [{cp}]: {reason}")
    sys.exit(1)


def _expected_rows_by_region(gt):
    import csv

    source_region = {}
    with open(REFERENCE_DIR / "sources.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            source_region[row["source_id"]] = row["region"]

    expected = {}
    for source_id, count in gt["rows_by_source"].items():
        region = source_region[source_id]
        expected[region] = expected.get(region, 0) + count
    return expected


def run_cp1():
    gt = load_ground_truth()
    mod = load_learner_module(TASK_ROOT / "src" / "pipeline.py", "pipeline")
    if not hasattr(mod, "build_silver"):
        _cp_fail("cp1", "src/pipeline.py has no build_silver(...) function")

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = SparkSession.builder.appName("08-capstone-cp1-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        print("running build_silver (this writes the lake) ...")
        try:
            report = mod.build_silver(spark, RAW_EVENTS_DIR, REFERENCE_DIR, SILVER_DEST)
        except NotImplementedError:
            _cp_fail("cp1", "scaffold not implemented yet (NotImplementedError)")
        except Exception as e:
            _cp_fail("cp1", f"build_silver() raised {type(e).__name__}: {e}")

        if not isinstance(report, dict) or not {"plan", "total_rows", "rows_by_month"} <= report.keys():
            _cp_fail("cp1", "build_silver() must return {'plan': str, 'total_rows': int, 'rows_by_month': dict}")

        plan = report["plan"]
        n_broadcast = plan.count("BroadcastHashJoin")
        if n_broadcast < 2:
            _cp_fail("cp1", f"returned plan shows {n_broadcast} BroadcastHashJoin occurrence(s), expected at least 2")
        if plan_has(plan, "SortMergeJoin"):
            _cp_fail("cp1", "returned plan contains a SortMergeJoin -- expected both reference joins to broadcast")

        # --- independent read-back of the lake ---
        try:
            lake_df = spark.read.parquet(SILVER_DEST)
        except Exception as e:
            _cp_fail("cp1", f"could not read {SILVER_DEST} after build_silver() returned: {type(e).__name__}: {e}")

        if "month" not in lake_df.columns:
            _cp_fail("cp1", f"lake at {SILVER_DEST} has no 'month' column")
        for col in ("region", "vertical", "tier"):
            if col not in lake_df.columns:
                _cp_fail("cp1", f"lake at {SILVER_DEST} is missing enrichment column '{col}'")

        counts = {
            row["month"]: row["cnt"]
            for row in lake_df.groupBy("month").agg(F.count(F.lit(1)).alias("cnt")).collect()
        }
        total = sum(counts.values())
        expected_rows_by_month = gt["rows_by_month"]

        missing = sorted(set(expected_rows_by_month) - set(counts))
        extra = sorted(set(counts) - set(expected_rows_by_month))
        if missing:
            _cp_fail("cp1", f"lake is missing month partition(s): {missing}")
        if extra:
            _cp_fail("cp1", f"lake has unexpected month partition(s): {extra}")
        mismatches = {m: (counts[m], expected_rows_by_month[m]) for m in expected_rows_by_month if counts[m] != expected_rows_by_month[m]}
        if mismatches:
            sample = dict(list(mismatches.items())[:5])
            _cp_fail("cp1", f"per-month row counts wrong for {len(mismatches)} month(s), e.g. {sample}")
        if total != gt["distinct_rows"]:
            _cp_fail("cp1", f"total rows in lake = {total}, expected ground-truth distinct_rows = {gt['distinct_rows']}")

        # --- region counts, derived independently, no Spark involved ---
        expected_region = _expected_rows_by_region(gt)
        actual_region = {
            row["region"]: row["cnt"]
            for row in lake_df.groupBy("region").agg(F.count(F.lit(1)).alias("cnt")).collect()
        }
        region_mismatches = {
            r: (actual_region.get(r), expected_region[r])
            for r in expected_region
            if actual_region.get(r) != expected_region[r]
        }
        if region_mismatches:
            _cp_fail("cp1", f"rows_by_region mismatch vs. sources.csv-derived expectation: {region_mismatches}")

        # --- layout: month= dirs, bounded file count per partition ---
        files_df = lake_df.withColumn("_f", F.input_file_name())
        file_rows = files_df.select("month", "_f").distinct().collect()
        files_per_month = {}
        for row in file_rows:
            files_per_month.setdefault(row["month"], set()).add(row["_f"])
            if f"month={row['month']}" not in row["_f"]:
                _cp_fail("cp1", f"file path for month={row['month']} does not contain its own month= segment: {row['_f']}")
        bad = {m: len(fs) for m, fs in files_per_month.items() if len(fs) > MAX_FILES_PER_MONTH or len(fs) == 0}
        if bad:
            sample = dict(list(bad.items())[:5])
            _cp_fail("cp1", f"file count per month partition out of bounds (1..{MAX_FILES_PER_MONTH}): {sample}")

        print(
            f"PASSED [cp1]: {total} rows across {len(counts)} months, "
            f"{n_broadcast} BroadcastHashJoin occurrence(s), rows_by_region matches"
        )
    finally:
        spark.stop()

    return True


def run_cp2():
    mod = load_learner_module(TASK_ROOT / "src" / "tuned.py", "tuned")
    for fn in ("run_naive", "run_tuned"):
        if not hasattr(mod, fn):
            _cp_fail("cp2", f"src/tuned.py has no {fn}(...) function")

    from pyspark.sql import SparkSession
    from pyspark.errors import AnalysisException

    spark = SparkSession.builder.appName("08-capstone-cp2-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        try:
            spark.read.parquet(SILVER_DEST).take(1)
        except (AnalysisException, Exception) as e:
            msg = str(e)
            if "Path does not exist" in msg or "does not exist" in msg or "NoSuchBucket" in msg or "404" in msg:
                _cp_fail("cp2", f"no silver lake found at {SILVER_DEST} -- run your CP1 job first (./run.sh .../tests/validate.py --cp1)")
            raise

        try:
            naive_df = mod.run_naive(spark, SILVER_DEST)
        except NotImplementedError:
            _cp_fail("cp2", "run_naive scaffold not implemented yet (NotImplementedError)")
        for col in ("region", "sum_delta", "avg_delta", "n"):
            if col not in naive_df.columns:
                _cp_fail("cp2", f"run_naive() result is missing column '{col}'")
        from harness.common import get_plan
        plan_naive = get_plan(naive_df, "formatted")
        rows_naive = {r["region"]: (r["sum_delta"], r["avg_delta"], r["n"]) for r in naive_df.collect()}

        try:
            tuned_df = mod.run_tuned(spark, SILVER_DEST)
        except NotImplementedError:
            _cp_fail("cp2", "run_tuned scaffold not implemented yet (NotImplementedError)")
        for col in ("region", "sum_delta", "avg_delta", "n"):
            if col not in tuned_df.columns:
                _cp_fail("cp2", f"run_tuned() result is missing column '{col}'")
        plan_tuned_before = get_plan(tuned_df, "formatted")
        rows_tuned = {r["region"]: (r["sum_delta"], r["avg_delta"], r["n"]) for r in tuned_df.collect()}
        plan_tuned_after = get_plan(tuned_df, "formatted")

        # --- identical results ---
        if set(rows_naive) != set(rows_tuned):
            _cp_fail("cp2", f"naive and tuned cover different regions: {sorted(rows_naive)} vs {sorted(rows_tuned)}")
        for region in rows_naive:
            sd_n, ad_n, n_n = rows_naive[region]
            sd_t, ad_t, n_t = rows_tuned[region]
            if n_n != n_t:
                _cp_fail("cp2", f"region {region}: n differs between naive ({n_n}) and tuned ({n_t})")
            approx(sd_t, sd_n, rel_tol=1e-6, what=f"region {region} sum_delta (tuned vs naive)")
            approx(ad_t, ad_n, rel_tol=1e-6, what=f"region {region} avg_delta (tuned vs naive)")

        # --- structural plan gate ---
        if not plan_has(plan_naive, "SortMergeJoin"):
            _cp_fail("cp2", "run_naive's plan has no SortMergeJoin -- expected the monthly-aggregate join to sort-merge under default settings")

        if "== Final Plan ==" in plan_tuned_after:
            final_section = plan_tuned_after.split("== Final Plan ==", 1)[1]
            if "== Initial Plan ==" in final_section:
                final_section = final_section.split("== Initial Plan ==", 1)[0]
        else:
            final_section = plan_tuned_after
        if not plan_has(final_section, "BroadcastHashJoin"):
            _cp_fail("cp2", "run_tuned's adopted plan has no BroadcastHashJoin -- expected the monthly-aggregate join to broadcast once tuned")
        if plan_has(final_section, "SortMergeJoin"):
            _cp_fail("cp2", "run_tuned's adopted plan still contains a SortMergeJoin -- expected it fully replaced by a broadcast join")

        # --- timing, informational-but-gated per results-local.json ---
        results = load_results(RESULTS_PATH, what="results-local.json (run tests/bench.py first)")
        for key in ("naive_seconds", "tuned_seconds"):
            if key not in results:
                _cp_fail("cp2", f"results-local.json missing '{key}' -- run tests/bench.py, don't hand-edit this file")
        naive_s, tuned_s = results["naive_seconds"], results["tuned_seconds"]
        if tuned_s > naive_s * MAX_TUNED_OVER_NAIVE_RATIO:
            _cp_fail(
                "cp2",
                f"tuned_seconds ({tuned_s:.2f}) is not clearly below naive_seconds ({naive_s:.2f}) -- "
                f"expected tuned <= {MAX_TUNED_OVER_NAIVE_RATIO} x naive; rerun tests/bench.py if this looks like a fluke",
            )

        print(
            f"PASSED [cp2]: results match across {len(rows_naive)} region(s); naive plan has SortMergeJoin, "
            f"tuned's final plan has BroadcastHashJoin only; tuned {tuned_s:.2f}s vs naive {naive_s:.2f}s"
        )
    finally:
        spark.stop()

    return True


def run_cp3():
    check_notes_filled(DESIGN_PATH, min_chars=1500, what="DESIGN.md")
    check_notes_filled(NOTES_PATH, min_chars=250, what="NOTES.md")
    print("PASSED [cp3]: DESIGN.md and NOTES.md both have real content")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cp1", action="store_true")
    ap.add_argument("--cp2", action="store_true")
    ap.add_argument("--cp3", action="store_true")
    args = ap.parse_args()

    selected = [flag for flag in (args.cp1, args.cp2, args.cp3) if flag]
    run_all = not selected

    try:
        if run_all or args.cp1:
            run_cp1()
        if run_all or args.cp2:
            run_cp2()
        if run_all or args.cp3:
            run_cp3()
    except SystemExit:
        raise
    except Exception as e:
        print(f"NOT PASSED: unexpected error: {type(e).__name__}: {e}")
        sys.exit(1)

    passed("cp1, cp2, cp3" if run_all else "requested checkpoint(s)")


if __name__ == "__main__":
    main()
