"""Broadcast vs sort-merge joins, and AQE's runtime join-strategy conversion.

All functions take a live `pyspark.sql.SparkSession` as their first argument
(the validator constructs it once and calls all three functions on that same
session in sequence — session config set by one function is still in effect
when the next one runs). Each function is explicit about the AQE and
autoBroadcastJoinThreshold configuration it needs — set both at the top of
every function, do not rely on whatever a previous function left behind:

    spark.conf.set("spark.sql.adaptive.enabled", "false" | "true")
    spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "...")

Raw JSONL rows have a top-level `_corrupt_record` column when a line fails
to parse as JSON — everywhere below, "drop unparseable lines" means
`filter(col("_corrupt_record").isNull())`.

"Deduplicate" always means whole-row `.distinct()` on the parsed events
(after dropping `_corrupt_record` rows), removing the retry-storm repeats
injected during generation.
"""

from pathlib import Path


def broadcast_enrich(spark, jsonl_dir: Path, reference_dir: Path) -> dict:
    """Enrich deduplicated events with sources.csv and categories.csv via broadcast joins.

    Steps:
      1. Read jsonl_dir, drop unparseable lines, deduplicate (whole-row
         .distinct()).
      2. Read reference_dir/sources.csv and reference_dir/categories.csv
         with header + inferred schema
         (spark.read.option("header", True).option("inferSchema", True).csv(...)).
      3. Join the deduplicated events to sources on source_id, and the
         result to categories on category_id. Force both joins to broadcast
         the (small) reference side with F.broadcast(...) — do not rely on
         spark.sql.autoBroadcastJoinThreshold alone, be explicit. Disable
         AQE first (spark.conf.set("spark.sql.adaptive.enabled", "false"))
         so the plan you capture is exactly what will execute, not an
         adaptive placeholder.
      4. Capture the joined DataFrame's plan with harness.common.get_plan.
      5. Compute two aggregates on the joined result:
         - row count grouped by `region` (from sources.csv)
         - row count grouped by `vertical` (from categories.csv)

    Returns:
        {
            "plan": str,                          # get_plan() of the fully joined DataFrame
            "deduped_row_count": int,              # row count after dedup, before any join
            "rows_by_region": {region: count, ...},
            "rows_by_vertical": {vertical: count, ...},
        }
    """
    raise NotImplementedError("implement broadcast_enrich")


def force_sort_merge(spark, jsonl_dir: Path) -> dict:
    """Force a sort-merge join between two large, comparably-sized monthly aggregates.

    Steps:
      1. spark.conf.set("spark.sql.adaptive.enabled", "false")
         spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "-1")
         (-1 disables auto-broadcast entirely, regardless of side size —
         this is what forces Spark's planner onto a sort-merge join for
         two sides neither of which is trivially tiny.)
      2. Read jsonl_dir, drop unparseable lines, keep http_status == 200
         rows, derive a `month` column from captured_at (first 7 chars,
         "YYYY-MM").
      3. Build per-(product_id, source_id) aggregates (e.g. avg(price),
         count(*)) for two different months — 2025-11 and 2025-12 give
         datasets with a meaningful season difference (see
         ground-truth.json's rows_by_month) and both aggregate down to a
         few thousand rows, comparable in size to each other, which is what
         keeps this an SMJ-vs-SMJ-alternative decision rather than a
         "one side is obviously the small one" case.
      4. Inner-join the two monthly aggregates on (product_id, source_id).
         Capture the plan.
      5. Correctness cross-check: build the exact same join again, but with
         F.broadcast(...) hinted on one side (the hint overrides the -1
         threshold). Its row count must equal the sort-merge join's row
         count — the join strategy must never change the result, only how
         it's computed.

    Returns:
        {
            "plan": str,                # get_plan() of the SMJ-forced join
            "row_count": int,           # row count of the SMJ-forced join
            "broadcast_row_count": int, # row count of the broadcast-hinted twin join
        }
    """
    raise NotImplementedError("implement force_sort_merge")


def aqe_converts_join(spark, jsonl_dir: Path) -> dict:
    """Show AQE converting a sort-merge join into a broadcast join at runtime.

    Steps:
      1. spark.conf.set("spark.sql.adaptive.enabled", "true"). Also
         explicitly reset spark.sql.autoBroadcastJoinThreshold to Spark's
         default (10485760, i.e. 10MB) — do not leave it at whatever
         force_sort_merge set it to (-1), since the validator runs all
         three functions on one shared SparkSession and config persists
         across calls. -1 here would prevent the exact conversion this
         function demonstrates.
      2. Read jsonl_dir, drop unparseable lines, keep http_status == 200
         rows, derive `month` the same way as force_sort_merge.
      3. Build per-product_id aggregates (avg(price), count(*)) for
         2025-11 and 2025-12 (product_id alone, not (product_id,
         source_id) — this keeps each side's aggregated size small enough
         that AQE's runtime statistics make the broadcast conversion kick
         in; the point of this function is the conversion, not the size of
         the join).
      4. Inner-join the two monthly aggregates on product_id. Do NOT call
         any action yet.
      5. Capture the plan with get_plan(joined, "formatted") *before* any
         action — with AQE on and nothing executed, this shows
         `AdaptiveSparkPlan` with `isFinalPlan=false`; the static planner's
         choice here is a sort-merge join, because at plan-build time
         nothing has told it either side is small.
      6. Call an action that materializes `joined` (e.g. joined.collect()).
      7. Capture the plan again on the *same* `joined` DataFrame. With AQE
         on, this now shows `isFinalPlan=true`, and the adopted "Final
         Plan" section contains a BroadcastHashJoin — AQE measured the
         actual shuffle output sizes at runtime and rewrote the join
         strategy, even though the initial (pre-execution) plan picked
         sort-merge.

    Returns:
        {
            "plan_before_action": str,  # get_plan() captured before step 6
            "plan_after_action": str,   # get_plan() captured after step 6
            "row_count": int,           # len(joined.collect()) from step 6
        }
    """
    raise NotImplementedError("implement aqe_converts_join")
