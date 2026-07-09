"""Validator for 03-joins-broadcast-vs-smj.

Needs a live SparkSession, so it runs inside the container:
    ./run.sh 03-joins-broadcast-vs-smj/tests/validate.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    RAW_EVENTS_DIR,
    REFERENCE_DIR,
    check_notes_filled,
    fail,
    get_plan,
    guarded,
    load_ground_truth,
    load_learner_module,
    passed,
    plan_has,
)


def _expected_rows_by_region(gt):
    """Independently derive rows_by_region from ground truth + sources.csv, no Spark."""
    region_of = {}
    with open(REFERENCE_DIR / "sources.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            region_of[row["source_id"]] = row["region"]
    by_region = defaultdict(int)
    for source_id, count in gt["rows_by_source"].items():
        by_region[region_of[source_id]] += count
    return dict(by_region)


def _final_plan_section(plan_text):
    """Slice out the '== Final Plan ==' section of an AQE-formatted plan, if present."""
    if "== Final Plan ==" not in plan_text:
        return None
    tail = plan_text.split("== Final Plan ==", 1)[1]
    if "== Initial Plan ==" in tail:
        tail = tail.split("== Initial Plan ==", 1)[0]
    return tail


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")
    if not (REFERENCE_DIR / "sources.csv").exists() or not (REFERENCE_DIR / "categories.csv").exists():
        fail(f"no reference tables at {REFERENCE_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()

    mod = load_learner_module(TASK_ROOT / "src" / "joins.py", "joins")
    for fn in ("broadcast_enrich", "force_sort_merge", "aqe_converts_join"):
        if not hasattr(mod, fn):
            fail(f"src/joins.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("03-joins-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        # --- broadcast_enrich ---
        be = mod.broadcast_enrich(spark, RAW_EVENTS_DIR, REFERENCE_DIR)
        if not isinstance(be, dict):
            fail(f"broadcast_enrich must return a dict, got {type(be).__name__}")
        for key in ("plan", "deduped_row_count", "rows_by_region", "rows_by_vertical"):
            if key not in be:
                fail(f"broadcast_enrich result missing key '{key}'")

        be_plan = be["plan"]
        if be_plan.count("BroadcastHashJoin") < 2:
            fail(
                "broadcast_enrich plan has fewer than 2 BroadcastHashJoin occurrences — "
                "expected both the sources and categories joins to broadcast"
            )
        if plan_has(be_plan, "SortMergeJoin"):
            fail("broadcast_enrich plan contains 'SortMergeJoin' — both joins should be broadcast, none sort-merge")

        if be["deduped_row_count"] != gt["distinct_rows"]:
            fail(
                f"broadcast_enrich deduped_row_count={be['deduped_row_count']}, "
                f"expected ground-truth distinct_rows={gt['distinct_rows']}"
            )

        expected_region = _expected_rows_by_region(gt)
        rows_by_region = {str(k): int(v) for k, v in be["rows_by_region"].items()}
        if set(rows_by_region.keys()) != set(expected_region.keys()):
            fail(
                f"rows_by_region keys {sorted(rows_by_region.keys())} != "
                f"expected {sorted(expected_region.keys())}"
            )
        for region, expected_count in expected_region.items():
            if rows_by_region[region] != expected_count:
                fail(
                    f"rows_by_region[{region}]={rows_by_region[region]}, expected {expected_count} "
                    "(derived independently from ground-truth rows_by_source + sources.csv)"
                )

        rows_by_vertical = {str(k): int(v) for k, v in be["rows_by_vertical"].items()}
        vertical_total = sum(rows_by_vertical.values())
        if vertical_total != gt["distinct_rows"]:
            fail(
                f"rows_by_vertical values sum to {vertical_total}, expected {gt['distinct_rows']} "
                "(every distinct event's category_id must join to exactly one categories.csv row)"
            )

        # --- force_sort_merge ---
        fsm = mod.force_sort_merge(spark, RAW_EVENTS_DIR)
        if not isinstance(fsm, dict):
            fail(f"force_sort_merge must return a dict, got {type(fsm).__name__}")
        for key in ("plan", "row_count", "broadcast_row_count"):
            if key not in fsm:
                fail(f"force_sort_merge result missing key '{key}'")

        fsm_plan = fsm["plan"]
        if not plan_has(fsm_plan, "SortMergeJoin"):
            fail("force_sort_merge plan does not contain 'SortMergeJoin'")
        if plan_has(fsm_plan, "BroadcastHashJoin"):
            fail("force_sort_merge plan contains 'BroadcastHashJoin' — expected a pure sort-merge join")

        if fsm["row_count"] <= 0:
            fail(f"force_sort_merge row_count={fsm['row_count']}, expected a positive row count")
        if fsm["row_count"] != fsm["broadcast_row_count"]:
            fail(
                f"force_sort_merge row_count={fsm['row_count']} != "
                f"broadcast_row_count={fsm['broadcast_row_count']} — "
                "join strategy must not change the result"
            )

        # --- aqe_converts_join ---
        aq = mod.aqe_converts_join(spark, RAW_EVENTS_DIR)
        if not isinstance(aq, dict):
            fail(f"aqe_converts_join must return a dict, got {type(aq).__name__}")
        for key in ("plan_before_action", "plan_after_action", "row_count"):
            if key not in aq:
                fail(f"aqe_converts_join result missing key '{key}'")

        plan_before = aq["plan_before_action"]
        plan_after = aq["plan_after_action"]

        if not plan_has(plan_before, "isFinalPlan=false"):
            fail(
                "aqe_converts_join plan_before_action does not show 'isFinalPlan=false' — "
                "expected the plan captured before any action to still be un-adapted"
            )
        if not plan_has(plan_after, "isFinalPlan=true"):
            fail(
                "aqe_converts_join plan_after_action does not show 'isFinalPlan=true' — "
                "expected the plan captured after materializing the DataFrame to be the adapted final plan"
            )

        final_section = _final_plan_section(plan_after)
        if final_section is None:
            fail("aqe_converts_join plan_after_action has no '== Final Plan ==' section")
        if "BroadcastHashJoin" not in final_section:
            fail(
                "aqe_converts_join's adopted Final Plan does not contain BroadcastHashJoin — "
                "expected AQE to convert the join to a broadcast at runtime"
            )

        if aq["row_count"] <= 0:
            fail(f"aqe_converts_join row_count={aq['row_count']}, expected a positive row count")

    finally:
        spark.stop()

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed("broadcast enrichment, forced sort-merge, and AQE runtime conversion all check out")


if __name__ == "__main__":
    main()
