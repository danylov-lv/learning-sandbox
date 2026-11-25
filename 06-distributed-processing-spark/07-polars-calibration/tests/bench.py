"""Timing harness for 07-polars-calibration: polars (host) vs Spark (container).

Fully implemented — not yours to edit. Two independent modes, selected by
whether "--spark" is on argv, so the same file can run in two very
different Python environments without either half importing a library the
other environment doesn't have:

  1. polars mode (default) — runs on the host via uv, calls YOUR
     src/calibrate.py end-to-end (cold scan through all three results) and
     times the whole thing:
         uv run python 07-polars-calibration/tests/bench.py

  2. spark mode — runs inside the module's Spark container via run.sh, and
     times a small, self-contained Spark twin of the exact same rollup job
     (measurement scaffolding only, using nothing beyond what tasks 01-03
     already taught — this does NOT import or call your src/calibrate.py,
     it exists purely to produce a comparable wall-clock number):
         ./run.sh 07-polars-calibration/tests/bench.py --spark

Both modes read-modify-write the same results-local.json, so either half
can be run first, missing, or re-run without clobbering the other. Run
both before tests/validate.py — it checks that both numbers are present,
not which one is smaller.
"""

import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import RAW_EVENTS_DIR, fail, guarded, load_ground_truth, load_learner_module  # noqa: E402

RESULTS_PATH = TASK_ROOT / "results-local.json"


def _write_result(key, wall_seconds, rows_verified):
    results = {}
    if RESULTS_PATH.exists():
        try:
            results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results = {}
    results[key] = {"wall_seconds": wall_seconds, "rows_verified": rows_verified}
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS_PATH} [{key}] wall_seconds={wall_seconds:.2f} rows_verified={rows_verified}")

    other = "spark" if key == "polars" else "polars"
    if other not in results:
        how = (
            "./run.sh 07-polars-calibration/tests/bench.py --spark"
            if other == "spark"
            else "uv run python 07-polars-calibration/tests/bench.py"
        )
        print(f"note: '{other}' half missing from results-local.json — run: {how}")


@guarded
def run_polars():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    mod = load_learner_module(TASK_ROOT / "src" / "calibrate.py", "calibrate")

    print("timing polars pipeline (cold scan -> monthly rollup, filter probe, top-3 per source) ...")
    t0 = time.perf_counter()
    lf = mod.load_events(RAW_EVENTS_DIR)
    monthly = mod.monthly_rollup(lf)
    probe = mod.filter_probe(lf)
    top3 = mod.top3_per_source(lf)
    wall_seconds = time.perf_counter() - t0

    rows_verified = sum(monthly.get("rows_by_month", {}).values()) if isinstance(monthly, dict) else 0
    print(f"  polars: {wall_seconds:.2f}s, probe rows={probe.get('rows') if isinstance(probe, dict) else '?'}, "
          f"sources ranked={len(top3) if isinstance(top3, dict) else '?'}")
    _write_result("polars", wall_seconds, rows_verified)


@guarded
def run_spark():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    spark = SparkSession.builder.appName("07-polars-calibration-spark-twin").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        print("timing Spark twin (cold scan -> dedup -> monthly rollup, filter probe, top-3 per source) ...")
        t0 = time.perf_counter()

        raw = spark.read.json(str(RAW_EVENTS_DIR / "*.jsonl"))
        events = raw.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record").distinct()
        events.cache()
        n_rows = events.count()

        monthly = (
            events.withColumn("month", F.substring("captured_at", 1, 7))
            .groupBy("month")
            .agg(
                F.count("*").alias("rows"),
                F.sum(F.when(F.col("http_status") == 200, F.col("price"))).alias("price_sum"),
            )
            .collect()
        )

        probe = (
            events.filter(
                (F.col("source_id") == 4)
                & (F.col("captured_at") >= "2025-09-01")
                & (F.col("captured_at") < "2025-11-01")
            )
            .select(
                F.count("*").alias("rows"),
                F.sum(F.when(F.col("http_status") == 200, F.col("price"))).alias("price_sum"),
            )
            .collect()
        )

        w = Window.partitionBy("source_id").orderBy(F.col("price").desc(), F.col("product_id").desc())
        top3 = (
            events.filter(F.col("http_status") == 200)
            .withColumn("rk", F.row_number().over(w))
            .filter(F.col("rk") <= 3)
            .collect()
        )

        wall_seconds = time.perf_counter() - t0
        print(f"  spark: {wall_seconds:.2f}s, rows={n_rows}, months={len(monthly)}, "
              f"probe_rows={probe[0]['rows'] if probe else '?'}, top3_rows={len(top3)}")
        _write_result("spark", wall_seconds, n_rows)
    finally:
        spark.stop()


def main():
    load_ground_truth()  # fail early with a clear message if data/ isn't generated
    if "--spark" in sys.argv:
        run_spark()
    else:
        run_polars()


if __name__ == "__main__":
    main()
