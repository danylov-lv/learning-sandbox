"""Timing harness for CP2: naive vs tuned shuffle-heavy analytical query.

Self-contained apart from importing your src/tuned.py functions — this
file is fully implemented, not yours to edit. It calls your run_naive and
run_tuned, times each via a noop write sink (materializes every shuffle
and join stage without collecting rows to the driver or writing bytes —
see the module README for why this is the clean way to time a Spark
query), and writes results-local.json.

Watch localhost:4040 while this runs: open it in a browser (or curl -sL
localhost:4040/) during either timed run. Record in NOTES.md, for both the
naive and tuned runs: number of stages, shuffle read/write bytes per
stage, and the task-duration spread within the widest stage (max vs
median task time) — that spread is the skew/shuffle-size signal a wall
clock alone doesn't show you.

Run from the module root (needs a live SparkSession, so via the
container):
    ./run.sh 08-capstone-scrape-lake/tests/bench.py
"""

import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import S3_BUCKET, fail, guarded, load_learner_module  # noqa: E402

SILVER_DEST = f"s3a://{S3_BUCKET}/capstone/silver"
RESULTS_PATH = TASK_ROOT / "results-local.json"


@guarded
def main():
    mod = load_learner_module(TASK_ROOT / "src" / "tuned.py", "tuned")
    for fn in ("run_naive", "run_tuned"):
        if not hasattr(mod, fn):
            fail(f"src/tuned.py has no {fn}(...) function")

    from pyspark.sql import SparkSession
    from pyspark.errors import AnalysisException

    spark = SparkSession.builder.appName("08-capstone-cp2-bench").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        try:
            probe = spark.read.parquet(SILVER_DEST)
            probe.take(1)
        except (AnalysisException, Exception) as e:
            msg = str(e)
            if "Path does not exist" in msg or "does not exist" in msg or "NoSuchBucket" in msg or "404" in msg:
                fail(
                    f"no silver lake found at {SILVER_DEST} — run your CP1 job first "
                    "(build_silver via a __main__ block in src/pipeline.py, see the README)"
                )
            raise

        # warm the underlying read once so neither timed run pays first-touch I/O cost
        warm = spark.read.parquet(SILVER_DEST)
        warm.cache()
        warm_rows = warm.count()
        print(f"silver lake warmed: {warm_rows} rows cached")

        print("\ntiming run_naive via noop sink ... (watch localhost:4040 now)")
        naive_df = mod.run_naive(spark, SILVER_DEST)
        t0 = time.perf_counter()
        naive_df.write.format("noop").mode("overwrite").save()
        naive_seconds = time.perf_counter() - t0
        print(f"  naive: {naive_seconds:.2f}s")

        print("\ntiming run_tuned via noop sink ... (watch localhost:4040 now)")
        tuned_df = mod.run_tuned(spark, SILVER_DEST)
        t0 = time.perf_counter()
        tuned_df.write.format("noop").mode("overwrite").save()
        tuned_seconds = time.perf_counter() - t0
        print(f"  tuned: {tuned_seconds:.2f}s")

        results = {
            "naive_seconds": naive_seconds,
            "tuned_seconds": tuned_seconds,
        }
        RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {RESULTS_PATH}")
        print(
            "reminder: this is a local[*] wall-clock comparison on one machine — record what "
            "the Spark UI's Stages tab showed (shuffle read/write, task duration spread) in "
            "NOTES.md, not just these two numbers."
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
