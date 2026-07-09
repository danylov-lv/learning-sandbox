"""Timing harness for 02-partitions-and-shuffles: naive vs salted per-source aggregation.

Self-contained — does not call your src/partitions.py, so it runs
regardless of how far along your implementation is. It's here so you can
watch localhost:4040 while it runs and see the difference in the Stages
tab (task duration spread within a stage) between the naive run and the
salted run, and so you have a machine-local timing number to reason
about. This is *not* the validator's gate — tests/validate.py checks the
row-distribution numbers your own skew_partition_counts() produces, not
these timings. Local-mode timing gains from salting can be modest (or
even a wash) on a single machine with a small dataset; that's expected
and worth writing about in NOTES.md, not something to chase by tuning
this script.

Run from the module root (needs a live SparkSession, so via the
container):
    ./run.sh 02-partitions-and-shuffles/tests/bench.py
"""

import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import RAW_EVENTS_DIR, fail, guarded  # noqa: E402

RESULTS_PATH = TASK_ROOT / "results-local.json"
N_SALT = 8


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = (
        SparkSession.builder.appName("02-partitions-bench")
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    try:
        df = spark.read.json(str(RAW_EVENTS_DIR / "*.jsonl"))
        valid = df.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")
        valid.cache()
        valid.count()  # materialize the cache before timing either variant

        print("timing naive groupBy(source_id) aggregation ...")
        t0 = time.perf_counter()
        naive = valid.groupBy("source_id").agg(F.sum("price").alias("price_sum"), F.count("*").alias("n"))
        naive.collect()
        naive_seconds = time.perf_counter() - t0
        print(f"  naive: {naive_seconds:.2f}s")

        print(f"timing salted aggregation (n_salt={N_SALT}) ...")
        t0 = time.perf_counter()
        salted = valid.withColumn("salt", (F.rand(seed=17) * N_SALT).cast("int"))
        partial = salted.groupBy("source_id", "salt").agg(
            F.sum("price").alias("price_sum"), F.count("*").alias("n")
        )
        final = partial.groupBy("source_id").agg(
            F.sum("price_sum").alias("price_sum"), F.sum("n").alias("n")
        )
        final.collect()
        salted_seconds = time.perf_counter() - t0
        print(f"  salted: {salted_seconds:.2f}s")

        results = {
            "naive_seconds": naive_seconds,
            "salted_seconds": salted_seconds,
            "n_salt": N_SALT,
        }
        RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {RESULTS_PATH}")
        print(
            "note: this is a local[*] wall-clock comparison of one specific salting shape — "
            "it is informational, see README/NOTES for why the row-distribution check is the real gate."
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
