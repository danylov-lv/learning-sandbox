"""Timing harness for 04-udfs-and-arrow: python UDF vs pandas_udf vs builtins.

Not yours to edit. This calls your src/udfs.py (unlike some other tasks'
bench scripts, it needs your implementation to time it — there's nothing
generic to measure here, the whole point is your three variants' relative
cost). It times each variant end-to-end with a `noop` write, which forces
full materialization of every row without paying for a collect() or an
actual write to disk. Writes results-local.json (gitignored, machine-local)
so tests/validate.py can compare timing ratios against a threshold chosen
for this machine, per the module convention of never gating on absolute
numbers.

Run from the module root (needs a live SparkSession, so via the
container):
    ./run.sh 04-udfs-and-arrow/tests/bench.py
"""

import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import RAW_EVENTS_DIR, fail, guarded, load_learner_module  # noqa: E402

RESULTS_PATH = TASK_ROOT / "results-local.json"


def _time_noop_write(df):
    t0 = time.perf_counter()
    df.write.format("noop").mode("overwrite").save()
    return time.perf_counter() - t0


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    mod = load_learner_module(TASK_ROOT / "src" / "udfs.py", "udfs")
    for fn in ("prepare_events", "with_python_udf", "with_pandas_udf", "with_builtins"):
        if not hasattr(mod, fn):
            fail(f"src/udfs.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("04-udfs-bench").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        events = mod.prepare_events(spark, RAW_EVENTS_DIR)
        events.cache()
        n = events.count()  # warm the cache before timing any variant
        print(f"prepared {n} events")

        results = {"n_rows": n}
        for name, fn in (
            ("python_udf", mod.with_python_udf),
            ("pandas_udf", mod.with_pandas_udf),
            ("builtins", mod.with_builtins),
        ):
            print(f"timing {name} ...")
            out = fn(spark, events)
            seconds = _time_noop_write(out)
            print(f"  {name}: {seconds:.2f}s")
            results[f"{name}_seconds"] = seconds

        RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {RESULTS_PATH}")
        print(
            f"python/builtin ratio: {results['python_udf_seconds'] / results['builtins_seconds']:.2f}x  "
            f"pandas/builtin ratio: {results['pandas_udf_seconds'] / results['builtins_seconds']:.2f}x  "
            f"python/pandas ratio: {results['python_udf_seconds'] / results['pandas_udf_seconds']:.2f}x"
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
