"""Lazy evaluation and query-plan exploration over the PriceWatch raw-events dump.

All functions take a live `pyspark.sql.SparkSession` as their first argument
(the validator constructs it). Every function must disable adaptive query
execution on any DataFrame operation it measures or plans

    spark.conf.set("spark.sql.adaptive.enabled", "false")

AQE reoptimizes plans and coalesces shuffle partitions at runtime, which
makes both job counts and plan shapes nondeterministic between builds vs
executions of the same DataFrame. Set this once per function, before you
build or run anything you're going to measure.

Raw JSONL rows have a top-level `_corrupt_record` column when a line fails
to parse as JSON (Spark's json reader convention) — everywhere below,
"drop unparseable lines" means `filter(col("_corrupt_record").isNull())`.
"""

from pathlib import Path


def job_counts_around_actions(spark) -> dict:
    """Prove transformations trigger no jobs and each action triggers exactly one.

    Steps, in order:
      1. Build a source DataFrame by reading data/raw-events/*.jsonl (path is
         your choice — a single part file is enough, this function is about
         job counting, not the dataset). Immediately after this read call,
         record the job count as "jobs_after_source": reading JSON without
         an explicit schema triggers its own schema-inference job, and that
         job is expected, real work — it is not part of what this function
         measures, so the baseline is taken *after* it, not before.
      2. Add at least two chained transformations (e.g. a filter and a
         select) to the source DataFrame, calling nothing that would
         execute it. Record "jobs_after_transform".
      3. Call one action on the transformed DataFrame (e.g. .count()).
         Record "jobs_after_action_1".
      4. Call a second, different action on the same transformed DataFrame
         (e.g. .collect() — fine at this scale on a filtered slice; do not
         .collect() an unfiltered multi-million-row DataFrame). Record
         "jobs_after_action_2".

    Use spark.sparkContext.statusTracker().getJobIdsForGroup() (called with
    no arguments) to read how many jobs the whole application has run so
    far — its length is your job count at that checkpoint.

    Returns:
        {
            "jobs_after_source": int,
            "jobs_after_transform": int,
            "jobs_after_action_1": int,
            "jobs_after_action_2": int,
        }
    """
    raise NotImplementedError("implement job_counts_around_actions")


def narrow_vs_wide_plans(spark, jsonl_dir: Path) -> dict:
    """Build a narrow-only pipeline and a wide pipeline over the same source; return both plans.

    Narrow pipeline: read jsonl_dir, drop unparseable lines, apply only
    row-at-a-time / partition-local operations (filter, select — no
    grouping, join, repartition, or distinct). No stage boundary should be
    required to compute it.

    Wide pipeline: read jsonl_dir, drop unparseable lines, apply a
    groupBy(...).agg(...) (e.g. count or sum per source_id). This requires
    a shuffle to bring matching keys together.

    Capture each pipeline's plan with harness.common.get_plan(df) — do not
    call df.explain() directly, its output goes to stdout, not to a string.

    Returns:
        {
            "narrow_plan": str,   # get_plan() output for the narrow pipeline
            "wide_plan": str,     # get_plan() output for the wide pipeline
        }
    """
    raise NotImplementedError("implement narrow_vs_wide_plans")


def bootstrap_parquet_slice(spark, jsonl_dir: Path, out_dir: Path) -> int:
    """Convert the raw JSONL dump to Parquet once, dropping unparseable lines only.

    Read every data/raw-events/*.jsonl file, drop rows where
    _corrupt_record is not null, and write everything else (duplicates
    included — you are not deduplicating here, just mirroring the valid
    JSON lines in a columnar format) to out_dir as Parquet.

    This is a one-time bootstrap so tasks 3 and 4 have something to compare
    against a JSONL scan — it is not the final lake (task 06 does that
    properly, partitioned, on MinIO).

    Args:
        spark: live SparkSession.
        jsonl_dir: directory containing part-*.jsonl.
        out_dir: directory to write Parquet into (create if missing).

    Returns:
        Number of rows written. Must equal ground-truth.json's
        total_rows_raw (every valid JSON line, duplicates included).
    """
    raise NotImplementedError("implement bootstrap_parquet_slice")


def pushdown_comparison(spark, jsonl_dir: Path, parquet_dir: Path) -> dict:
    """Run the same filter+projection query against JSONL and against Parquet; return both plans.

    Build, for each source, the exact same logical query: read the source,
    filter to source_id == 4 and captured_at in
    ["2025-09-01", "2025-11-01") (half-open — this matches the inclusive
    2025-10-31 end date used elsewhere in this task), select only
    source_id and price, and aggregate (e.g. count and sum(price)). Do not
    call .distinct() here — this function is about scan-level pushdown and
    pruning, not deduplication (that is what dedup_filter_probe is for; the
    numbers from this function's aggregation are not checked against
    ground truth and may include retry-storm duplicates).

    Capture each side's plan with harness.common.get_plan(df).

    Returns:
        {
            "jsonl_plan": str,
            "parquet_plan": str,
        }
    """
    raise NotImplementedError("implement pushdown_comparison")


def dedup_filter_probe(spark, jsonl_dir: Path) -> dict:
    """Compute the exact filter_probe aggregate defined in ground-truth.json.

    Read every data/raw-events/*.jsonl file, drop rows where
    _corrupt_record is not null, deduplicate exact retry-storm repeats
    (whole-row equality — every column, including nested attrs), then
    filter to source_id == 4 and captured_at in the inclusive range
    2025-09-01 .. 2025-10-31.

    Returns:
        {
            "rows": int,            # row count of the filtered, deduped slice
            "price_sum": float,     # sum(price) over that slice, restricted
                                     # to rows with http_status == 200
                                     # (non-200 rows have price == null)
        }

    Must match ground-truth.json's filter_probe.rows / filter_probe.price_sum.
    """
    raise NotImplementedError("implement dedup_filter_probe")
