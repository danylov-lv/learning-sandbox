"""Validator for 01-lazy-plans-and-explain.

Needs a live SparkSession, so it runs inside the container:
    ./run.sh 01-lazy-plans-and-explain/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    RAW_EVENTS_DIR,
    approx,
    check_notes_filled,
    fail,
    get_plan,
    guarded,
    load_ground_truth,
    load_learner_module,
    passed,
    plan_has,
)

OUT_PARQUET_DIR = TASK_ROOT / "data" / "bootstrap.parquet"


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()

    mod = load_learner_module(TASK_ROOT / "src" / "explore.py", "explore")
    for fn in (
        "job_counts_around_actions",
        "narrow_vs_wide_plans",
        "bootstrap_parquet_slice",
        "pushdown_comparison",
        "dedup_filter_probe",
    ):
        if not hasattr(mod, fn):
            fail(f"src/explore.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("01-lazy-plans-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        # --- job_counts_around_actions ---
        jc = mod.job_counts_around_actions(spark)
        if not isinstance(jc, dict):
            fail(f"job_counts_around_actions must return a dict, got {type(jc).__name__}")
        for key in ("jobs_after_source", "jobs_after_transform", "jobs_after_action_1", "jobs_after_action_2"):
            if key not in jc:
                fail(f"job_counts_around_actions result missing key '{key}'")

        delta_transform = jc["jobs_after_transform"] - jc["jobs_after_source"]
        if delta_transform != 0:
            fail(
                f"building transformations triggered {delta_transform} job(s) — "
                "transformations should be lazy and trigger zero jobs"
            )
        delta_action_1 = jc["jobs_after_action_1"] - jc["jobs_after_transform"]
        if delta_action_1 != 1:
            fail(f"first action triggered {delta_action_1} job(s), expected exactly 1")
        delta_action_2 = jc["jobs_after_action_2"] - jc["jobs_after_action_1"]
        if delta_action_2 != 1:
            fail(f"second action triggered {delta_action_2} job(s), expected exactly 1")

        # --- narrow_vs_wide_plans ---
        plans = mod.narrow_vs_wide_plans(spark, RAW_EVENTS_DIR)
        if not isinstance(plans, dict) or "narrow_plan" not in plans or "wide_plan" not in plans:
            fail("narrow_vs_wide_plans must return {'narrow_plan': str, 'wide_plan': str}")

        if plan_has(plans["narrow_plan"], "Exchange"):
            fail("narrow_plan contains 'Exchange' — a narrow-only pipeline should need no shuffle")
        if not plan_has(plans["wide_plan"], "Exchange"):
            fail("wide_plan does not contain 'Exchange' — a groupBy aggregation should require a shuffle")

        # --- bootstrap_parquet_slice ---
        OUT_PARQUET_DIR.parent.mkdir(parents=True, exist_ok=True)
        rows_written = mod.bootstrap_parquet_slice(spark, RAW_EVENTS_DIR, OUT_PARQUET_DIR)
        if not isinstance(rows_written, int):
            fail(f"bootstrap_parquet_slice must return an int row count, got {type(rows_written).__name__}")
        if rows_written != gt["total_rows_raw"]:
            fail(
                f"bootstrap_parquet_slice wrote {rows_written} rows, expected "
                f"{gt['total_rows_raw']} (ground-truth total_rows_raw — all valid lines, duplicates included)"
            )

        # --- pushdown_comparison ---
        push = mod.pushdown_comparison(spark, RAW_EVENTS_DIR, OUT_PARQUET_DIR)
        if not isinstance(push, dict) or "jsonl_plan" not in push or "parquet_plan" not in push:
            fail("pushdown_comparison must return {'jsonl_plan': str, 'parquet_plan': str}")

        jsonl_plan = push["jsonl_plan"]
        parquet_plan = push["parquet_plan"]

        if not plan_has(parquet_plan, r"Batched:\s*true"):
            fail("parquet_plan scan does not show 'Batched: true' — expected the vectorized columnar reader")
        if plan_has(jsonl_plan, r"Batched:\s*true"):
            fail("jsonl_plan scan shows 'Batched: true' — JSON scans should not use the vectorized reader")
        if not plan_has(parquet_plan, r"PushedFilters:\s*\[[^\]]+\]"):
            fail("parquet_plan scan has no non-empty PushedFilters list")

        for label, plan_text in (("jsonl_plan", jsonl_plan), ("parquet_plan", parquet_plan)):
            for unrelated_col in ("title", "attrs", "url"):
                if f"{unrelated_col}:" in plan_text.split("ReadSchema:", 1)[-1].split("\n", 1)[0]:
                    fail(
                        f"{label} ReadSchema still includes unselected column '{unrelated_col}' — "
                        "expected column pruning to have dropped it"
                    )

        # --- dedup_filter_probe ---
        probe = mod.dedup_filter_probe(spark, RAW_EVENTS_DIR)
        if not isinstance(probe, dict) or "rows" not in probe or "price_sum" not in probe:
            fail("dedup_filter_probe must return {'rows': int, 'price_sum': float}")

        expected = gt["filter_probe"]
        if probe["rows"] != expected["rows"]:
            fail(f"dedup_filter_probe rows={probe['rows']}, expected {expected['rows']}")
        approx(probe["price_sum"], expected["price_sum"], rel_tol=1e-6, what="dedup_filter_probe price_sum")

    finally:
        spark.stop()

    # The unfilled template already scores ~441 chars (pre-filled ground-truth
    # table rows and the Postgres-parallel prompt), so the default 200 would
    # never fire; 650 requires ~200 chars of actual learner content on top.
    check_notes_filled(TASK_ROOT / "NOTES.md", min_chars=650)

    passed("job counts, narrow/wide plans, pushdown comparison, and filter_probe all check out")


if __name__ == "__main__":
    main()
