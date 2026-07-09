"""CP1 — raw scraped dumps to a clean, enriched, partitioned silver lake.

Takes a live `pyspark.sql.SparkSession` as its first argument. Reuses the
same conventions as tasks 01-06 in this module:

    spark.conf.set("spark.sql.adaptive.enabled", "false")

before building anything you intend to capture a plan on — AQE can rewrite
a join into a broadcast at runtime and would make the *pre-execution* plan
you capture here misleading about what a static planner actually chose.

Raw JSONL rows have a top-level `_corrupt_record` column when a line fails
to parse as JSON — "drop unparseable lines" means
`filter(col("_corrupt_record").isNull())`, then drop that column.

"Deduplicate" always means whole-row `.distinct()` on the parsed events
(after dropping `_corrupt_record`), removing the retry-storm repeats
injected during generation.

`captured_at` is an ISO-8601 string like "2025-09-14T03:11:07Z"; derive the
partition column `month` as its first 7 characters ("2025-09").

This task's silver lake lives at a fixed path,
`s3a://price-lake-05/capstone/silver` — the validator reads from that
exact path. Do not write anywhere else under `price-lake-05` except the
`capstone/` prefix — task 06 owns `task-06/` in the same bucket.
"""

from pathlib import Path


def build_silver(spark, jsonl_dir: Path, reference_dir: Path, dest: str) -> dict:
    """Clean, dedup, enrich, and write the raw events as a month-partitioned silver lake.

    Steps:
      1. Read every part-*.jsonl file under jsonl_dir.
      2. Drop rows where _corrupt_record is not null, then drop that column.
      3. Deduplicate exact retry-storm repeats (whole-row equality — every
         column, including nested attrs).
      4. Read reference_dir/sources.csv and reference_dir/categories.csv
         with header + inferred schema
         (spark.read.option("header", True).option("inferSchema", True).csv(...)).
      5. Disable AQE, then join the deduplicated events to sources on
         source_id and the result to categories on category_id, forcing
         both joins to broadcast the (small) reference side with
         F.broadcast(...) — do not rely on
         spark.sql.autoBroadcastJoinThreshold alone, be explicit. This adds
         (at least) `region` and `tier` from sources.csv and `vertical`
         from categories.csv to every row. It is an inner join on both
         sides — every event's source_id and category_id are guaranteed to
         match exactly one reference row (verified in task 03), so no rows
         are dropped or duplicated by either join.
      6. Capture this twice-joined DataFrame's plan with
         harness.common.get_plan *before* doing anything below — the
         validator checks this plan for two BroadcastHashJoin occurrences
         and no SortMergeJoin.
      7. Derive a `month` column: the first 7 characters of captured_at
         ("YYYY-MM").
      8. Repartition the DataFrame so that each month's rows land in a
         bounded, small number of in-memory partitions *before* the write —
         plain write.partitionBy("month") on its own only controls the
         output *directory* layout, not how many Spark tasks (and
         therefore how many output files) land in each directory (see task
         06's write_month_partitioned docstring for the full argument).
         repartition("month") collapses each month down to exactly one
         in-memory partition; repartition(N, "month") gives you up to N
         file-producing tasks per month if you want more write
         parallelism at larger scale. Either is acceptable here as long as
         the file count per month partition stays small and bounded (the
         validator checks this, see README).
      9. Write to dest (an s3a:// URI) as Parquet, partitioned by month,
         overwrite mode.

    Args:
        spark: live SparkSession.
        jsonl_dir: directory containing part-*.jsonl (on the host/container
            filesystem, not s3a).
        reference_dir: directory containing sources.csv and categories.csv.
        dest: s3a:// URI to write the partitioned silver lake to. Use
            exactly "s3a://price-lake-05/capstone/silver" in whatever
            driver code (a __main__ block in this file, or a separate
            script) you use to actually run the write job via ./run.sh.

    Returns:
        {
            "plan": str,             # get_plan() from step 6, the joined
                                      # DataFrame's plan, captured before
                                      # month derivation / repartition / write
            "total_rows": int,       # rows written, i.e. deduped row count
            "rows_by_month": {"2025-01": int, ..., "2026-06": int},
        }

    total_rows must equal ground-truth.json's distinct_rows. rows_by_month
    must match ground-truth.json's rows_by_month key for key.
    """
    raise NotImplementedError("implement build_silver")
