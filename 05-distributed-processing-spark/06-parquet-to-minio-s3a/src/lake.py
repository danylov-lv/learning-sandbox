"""Write and read a month-partitioned Parquet lake on MinIO (s3a) for PriceWatch.

All functions take a live `pyspark.sql.SparkSession` as their first argument.
Set `spark.conf.set("spark.sql.adaptive.enabled", "false")` at the top of any
function that inspects a plan or counts files — AQE can reshape both.

Raw JSONL rows have a top-level `_corrupt_record` column when a line fails to
parse as JSON — "drop unparseable lines" means `filter(col("_corrupt_record").isNull())`.

`captured_at` is an ISO-8601 string like "2025-09-14T03:11:07Z"; derive the
partition column `month` as its first 7 characters ("2025-09").

Every `dest` argument here is an `s3a://` URI. This task's lake lives under
`s3a://price-lake-05/task-06/lake` — a fixed path the validator reads from
directly, so use that exact path in whatever driver code (a `__main__` block
in this file, or a separate script) you use to actually run the write job via
`./run.sh`. Do not write anywhere else under `price-lake-05` except the
`task-06/` prefix — a later capstone task shares that bucket.
"""

from pathlib import Path


def write_month_partitioned(spark, jsonl_dir: Path, dest: str) -> dict:
    """Clean, dedup, and write the raw events to dest as Parquet partitioned by month.

    Steps:
      1. Read every part-*.jsonl file under jsonl_dir.
      2. Drop rows where _corrupt_record is not null (and drop that column).
      3. Deduplicate exact retry-storm repeats (whole-row equality — every
         column, including nested attrs).
      4. Derive a `month` column: the first 7 characters of captured_at
         ("YYYY-MM").
      5. Repartition the DataFrame by the `month` column *before* writing —
         write.partitionBy("month") on its own only controls the output
         *directory* layout; it does nothing about how many Spark tasks (and
         therefore how many output files) land in each of those directories.
         Every in-memory partition that contains rows for a given month
         writes its own file into that month's directory, so without an
         explicit repartition("month") first, you get roughly as many files
         per month as there are input partitions that happened to contain
         rows for that month — a spray of small files, not the one-file-per-
         partition layout this function is required to produce. Repartitioning
         by the same column you are about to partitionBy on collapses each
         month's rows into a single in-memory partition first, so the write
         stage emits exactly one file per month directory.
      6. Write to dest (an s3a:// URI) as Parquet, partitioned by month,
         overwrite mode.

    Args:
        spark: live SparkSession.
        jsonl_dir: directory containing part-*.jsonl (on the host/container
            filesystem, not s3a).
        dest: s3a:// URI to write the partitioned Parquet lake to.

    Returns:
        {
            "rows_by_month": {"2025-01": int, ..., "2026-06": int},
            "total_rows": int,   # sum of rows_by_month, i.e. rows actually written
        }

    rows_by_month must match ground-truth.json's rows_by_month key for key,
    and total_rows must equal ground-truth.json's distinct_rows.
    """
    raise NotImplementedError("implement write_month_partitioned")


def inspect_lake_files(spark, dest: str) -> dict:
    """Report the on-disk (on-s3a) file layout of a lake written by write_month_partitioned.

    Read dest back with spark.read.parquet(dest) and, using
    pyspark.sql.functions.input_file_name(), determine for each distinct
    month value the set of distinct file paths that contain rows for that
    month, and the count of files in that set.

    Args:
        spark: live SparkSession.
        dest: s3a:// URI of a previously-written lake (see write_month_partitioned).

    Returns:
        {
            "files_per_month": {"2025-01": int, ..., "2026-06": int},
                # number of distinct Parquet files under that month's partition
            "all_paths_have_month_dir": bool,
                # True iff every distinct file path contains "month=<the same
                # month value that row reported>" as a path segment
        }

    A correctly-written lake (per write_month_partitioned's contract) has
    files_per_month[m] == 1 for every month m, and
    all_paths_have_month_dir == True.
    """
    raise NotImplementedError("implement inspect_lake_files")


def pruned_read(spark, dest: str, month: str) -> dict:
    """Read the lake with a month filter and prove partition pruning actually happened.

    Build `spark.read.parquet(dest).filter(col("month") == month)`. Do not
    call anything that forces materialization before capturing the plan.

    Args:
        spark: live SparkSession.
        dest: s3a:// URI of a previously-written lake.
        month: a single "YYYY-MM" value to filter to.

    Returns:
        {
            "plan": str,               # harness.common.get_plan(df, "formatted")
                                        # captured on the filtered DataFrame
                                        # before any action runs
            "row_count": int,          # df.count() after capturing the plan
            "distinct_files_touched": int,
                # number of distinct input_file_name() values among the rows
                # returned by the filtered read (an action — run it after you
                # already have "plan" and "row_count")
        }

    row_count must equal ground-truth.json's rows_by_month[month].
    distinct_files_touched must be exactly 1 (one file, in one month=<month>
    directory — see write_month_partitioned's one-file-per-partition
    contract) if the write was done correctly.
    """
    raise NotImplementedError("implement pruned_read")
