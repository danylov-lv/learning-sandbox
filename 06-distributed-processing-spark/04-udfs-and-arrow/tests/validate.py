"""Validator for 04-udfs-and-arrow.

Needs a live SparkSession, so it runs inside the container:
    ./run.sh 04-udfs-and-arrow/tests/validate.py
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
    get_plan,
    load_learner_module,
    load_results,
    passed,
    plan_has,
)

RESULTS_PATH = TASK_ROOT / "results-local.json"

# Empirically measured on the reference machine (pyspark 3.5.3, 2M-row
# dataset, noop-write timing via tests/bench.py): plain UDF was ~6-9x the
# builtins wall time, pandas_udf ~2x the plain UDF. Gates below sit with
# generous slack under both observed floors.
PYTHON_VS_BUILTIN_MIN_RATIO = 3.0
PYTHON_VS_PANDAS_MIN_RATIO = 1.3


def _reference_fingerprint(spark, jsonl_dir):
    """Validator-owned, built-ins-only computation of the same aggregate.

    Deliberately independent of the learner's prepare_events/with_builtins
    so a bug in either doesn't silently agree with itself. Kept minimal —
    this is a checker, not something to crib for the actual task.
    """
    from pyspark.sql import functions as F

    df = spark.read.json(str(jsonl_dir / "*.jsonl"))
    valid = df.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")
    valid = valid.distinct().filter(F.col("http_status") == 200)
    valid = valid.withColumn("weight_g", F.col("attrs")["weight_g"].cast("double"))
    valid = valid.withColumn(
        "bucket",
        F.when(F.col("price").isNull(), "unknown")
        .when(F.col("price") < 20, "low")
        .when(F.col("price") < 100, "mid")
        .otherwise("high"),
    )
    return _fingerprint(valid)


def _fingerprint(df):
    from pyspark.sql import functions as F

    bucket_counts = {
        row["bucket"]: row["n"]
        for row in df.groupBy("bucket").agg(F.count("*").alias("n")).collect()
    }
    agg = df.agg(
        F.count(F.col("weight_g")).alias("weight_g_nonnull"),
        F.round(F.sum("weight_g"), 2).alias("weight_g_sum"),
    ).collect()[0]
    return {
        "bucket_counts": bucket_counts,
        "weight_g_nonnull": agg["weight_g_nonnull"],
        "weight_g_sum": float(agg["weight_g_sum"]) if agg["weight_g_sum"] is not None else None,
    }


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    mod = load_learner_module(TASK_ROOT / "src" / "udfs.py", "udfs")
    for fn in ("prepare_events", "with_python_udf", "with_pandas_udf", "with_builtins"):
        if not hasattr(mod, fn):
            fail(f"src/udfs.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("04-udfs-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        events = mod.prepare_events(spark, RAW_EVENTS_DIR)
        events.cache()
        events.count()

        expected_cols = {"product_id", "source_id", "price", "attrs"}
        if set(events.columns) != expected_cols:
            fail(f"prepare_events columns {sorted(events.columns)} != expected {sorted(expected_cols)}")

        variants = {}
        for name, fn in (
            ("python_udf", mod.with_python_udf),
            ("pandas_udf", mod.with_pandas_udf),
            ("builtins", mod.with_builtins),
        ):
            out = fn(spark, events)
            out_cols = set(out.columns)
            expected_out_cols = {"product_id", "source_id", "price", "weight_g", "bucket"}
            if out_cols != expected_out_cols:
                fail(f"with_{name}'s output columns {sorted(out_cols)} != expected {sorted(expected_out_cols)}")
            variants[name] = out

        # --- plan-structure ---
        python_plan = get_plan(variants["python_udf"])
        if not plan_has(python_plan, "BatchEvalPython"):
            fail("with_python_udf's plan has no BatchEvalPython — expected a plain (non-Arrow) Python UDF eval node")
        if plan_has(python_plan, "ArrowEvalPython"):
            fail("with_python_udf's plan has ArrowEvalPython — that's the pandas_udf/Arrow path, not a plain udf()")

        pandas_plan = get_plan(variants["pandas_udf"])
        if not plan_has(pandas_plan, "ArrowEvalPython"):
            fail("with_pandas_udf's plan has no ArrowEvalPython — expected an Arrow-vectorized eval node")
        if plan_has(pandas_plan, "BatchEvalPython"):
            fail("with_pandas_udf's plan has BatchEvalPython — that's the plain-udf path, not pandas_udf")

        builtins_plan = get_plan(variants["builtins"])
        if plan_has(builtins_plan, "BatchEvalPython") or plan_has(builtins_plan, "ArrowEvalPython"):
            fail("with_builtins's plan has a Python eval node — expected no Python UDF at all, built-ins only")

        # --- correctness ---
        fingerprints = {name: _fingerprint(df) for name, df in variants.items()}
        base = fingerprints["python_udf"]
        for name in ("pandas_udf", "builtins"):
            if fingerprints[name] != base:
                fail(
                    f"with_{name}'s aggregate fingerprint {fingerprints[name]} != "
                    f"with_python_udf's {base} — the three variants must agree exactly"
                )

        reference = _reference_fingerprint(spark, RAW_EVENTS_DIR)
        if base != reference:
            fail(
                f"learner fingerprint {base} != validator's independent built-in reference {reference} — "
                "check the weight_g extraction and bucket thresholds"
            )

    finally:
        spark.stop()

    # --- timing ---
    results = load_results(RESULTS_PATH, what="results-local.json")
    for key in ("python_udf_seconds", "pandas_udf_seconds", "builtins_seconds"):
        if key not in results:
            fail(f"results-local.json missing '{key}' — run tests/bench.py first")

    python_s = results["python_udf_seconds"]
    pandas_s = results["pandas_udf_seconds"]
    builtins_s = results["builtins_seconds"]

    if builtins_s <= 0:
        fail(f"builtins_seconds={builtins_s} is not a usable positive timing")

    python_vs_builtin = python_s / builtins_s
    if python_vs_builtin < PYTHON_VS_BUILTIN_MIN_RATIO:
        fail(
            f"python_udf/builtins wall-time ratio ({python_vs_builtin:.2f}) is below the expected floor "
            f"({PYTHON_VS_BUILTIN_MIN_RATIO}) — the plain Python UDF should be measurably slower than built-ins"
        )

    if pandas_s <= 0:
        fail(f"pandas_udf_seconds={pandas_s} is not a usable positive timing")

    python_vs_pandas = python_s / pandas_s
    if python_vs_pandas < PYTHON_VS_PANDAS_MIN_RATIO:
        fail(
            f"python_udf/pandas_udf wall-time ratio ({python_vs_pandas:.2f}) is below the expected floor "
            f"({PYTHON_VS_PANDAS_MIN_RATIO}) — pandas_udf should be measurably faster than the plain UDF"
        )

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"plans, fingerprints, and timings all check out "
        f"(python/builtin={python_vs_builtin:.2f}x, python/pandas={python_vs_pandas:.2f}x)"
    )


if __name__ == "__main__":
    main()
