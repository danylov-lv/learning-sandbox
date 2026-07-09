"""Delta Lake pipeline over the price-snapshot data, using delta-rs (no Spark).

Column contract (same 13 columns as the earlier tasks, plus a derived
`month` partition column):

    product_id      int64
    source_id       int64
    url             string
    title           string
    category        string
    brand           string
    price           float64, nullable
    currency        string
    in_stock        bool, nullable
    captured_at     timestamp[us, tz=UTC]
    attrs           string (the nested "attrs" dict re-serialized as JSON text)
    scrape_run_id   string
    http_status     int64
    month           string, "YYYY-MM" derived from captured_at (UTC)

Non-200 rows carry price/in_stock as null in the source data already — keep
them null, never coerce to 0 / False.

Four functions, implement all of them. See the module README for the full
task description and completion criteria.
"""

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT))
# harness.common has the MinIO endpoint/credentials (minio_endpoint(), S3_ACCESS_KEY,
# S3_SECRET_KEY, S3_BUCKET) needed to build storage_options for s3:// table_uris.


def initial_load(raw_dir: Path, table_uri: str) -> int:
    """Write every month except the chronologically last one as a new Delta table.

    Args:
        raw_dir: directory containing part-*.jsonl input files.
        table_uri: local path, or an s3:// URI, to create the Delta table
            at. Must not already exist when this is called (this is the
            table's first commit). If table_uri is an s3:// URI, this
            function is also responsible for building the storage_options
            dict write_deltalake needs to reach MinIO (endpoint, access
            key, secret key from harness.common, plus whatever flags make
            delta-rs accept a plain-http, non-AWS S3 endpoint) and passing
            it through. Local paths need no storage_options.

    Behavior:
        - Determine the chronologically last month present in raw_dir first
          (a lightweight pass over captured_at is enough for this — you do
          not need to fully parse every row twice).
        - Stream the rest of the data (every row NOT in that last month),
          in bounded-size chunks, and write it as a Delta table partitioned
          by the derived `month` column, zstd-compressed.
        - This must land as exactly ONE commit (table version 0), even
          though you produce the data in a streaming/chunked fashion.
          delta-rs's write function accepts a streaming Arrow source
          (something exposing the Arrow C Stream interface, e.g. a
          pyarrow.RecordBatchReader built from a generator of RecordBatches)
          as its data argument, which lets you stream without holding the
          whole dataset in memory AND without producing more than one commit.

    Returns:
        Total number of rows written (every row except the last month's).
    """
    raise NotImplementedError(
        "implement initial_load: stream raw_dir excluding the last month into a new "
        "single-commit, month-partitioned, zstd-compressed Delta table at table_uri"
    )


def append_last_month(raw_dir: Path, table_uri: str) -> int:
    """Append the held-back last month's rows across multiple separate commits.

    Args:
        raw_dir: directory containing part-*.jsonl input files.
        table_uri: path (local or s3://) to the existing Delta table created
            by initial_load. Same storage_options handling as initial_load
            applies when table_uri is an s3:// URI.

    Behavior:
        - Re-scan raw_dir for rows belonging to the chronologically last
          month (the one initial_load excluded).
        - Split those rows into several fixed-size batches (a few thousand
          rows each is reasonable) and write each batch as its own
          mode="append" commit — do not combine them into a single write.
          This deliberately produces many small commits landing many small
          files in that month's partition, which is what a real scraper
          flushing incrementally does, and what src/delta_pipeline.py's
          compact() step exists to fix.

    Returns:
        Total number of rows appended (across all the append commits).
    """
    raise NotImplementedError(
        "implement append_last_month: append the held-back month in multiple "
        "separate mode='append' commits, not one"
    )


def add_price_bucket(table_uri: str) -> None:
    """Add a nullable price_bucket string column to the table's schema.

    This is a schema-only change: no existing data file is rewritten, and
    rows written before this call keep price_bucket implicitly null. Use
    the Delta table's ALTER TABLE ADD COLUMNS equivalent (schema evolution),
    not a full rewrite (e.g. mode="overwrite" with schema_mode="overwrite").

    A table opened at a version before this call must still report the
    schema WITHOUT price_bucket — that is the whole point of recording
    schema changes as their own commit rather than mutating files in place.

    Args:
        table_uri: path to the existing Delta table.
    """
    raise NotImplementedError(
        "implement add_price_bucket: evolve the table schema to add a nullable "
        "price_bucket string column without rewriting any data files"
    )


def compact(table_uri: str) -> dict:
    """Bin-pack the last month's many small append files into few larger ones, then vacuum.

    Behavior:
        - Run the table's file-compaction operation (OPTIMIZE-equivalent).
          This adds new, larger files that logically replace the small ones
          and removes the small files' entries from the live table view —
          but the small files' bytes are NOT deleted yet, they are only no
          longer referenced by the latest version.
        - Run vacuum to actually delete the now-unreferenced files from
          disk. The default vacuum retention window (commonly 7 days)
          exists specifically to protect concurrent readers who might still
          have the pre-compaction version open, and to keep recent time
          travel working. For this task, override the retention so vacuum
          deletes immediately — do this ONLY because this is a throwaway
          practice table with no concurrent readers; document in NOTES.md
          why you would not do this against a table anyone else might be
          reading.

    Args:
        table_uri: path to the existing Delta table.

    Returns:
        The metrics dict returned by the compaction call (whatever keys it
        actually contains — read them back rather than assuming names).
    """
    raise NotImplementedError(
        "implement compact: run file compaction, then vacuum with an overridden "
        "retention window so the old small files are actually deleted"
    )


if __name__ == "__main__":
    RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
    TABLE_URI = str(Path(__file__).resolve().parents[2] / "data" / "delta" / "snapshots")

    rows0 = initial_load(RAW_DIR, TABLE_URI)
    print(f"initial_load: {rows0} rows")

    rows1 = append_last_month(RAW_DIR, TABLE_URI)
    print(f"append_last_month: {rows1} rows")

    add_price_bucket(TABLE_URI)
    print("add_price_bucket: done")

    metrics = compact(TABLE_URI)
    print(f"compact: {metrics}")

    # Repeat steps 1-2 (only) against MinIO. Figure out the storage_options
    # write_deltalake/DeltaTable need to talk to a non-AWS S3-compatible
    # endpoint (see harness.common for the MinIO endpoint/credentials, and
    # hint-3 if you get stuck). No schema evolution or compaction on this leg.
    S3_TABLE_URI = "s3://price-lake/delta/snapshots"

    s3_rows0 = initial_load(RAW_DIR, S3_TABLE_URI)
    print(f"s3 initial_load: {s3_rows0} rows")

    s3_rows1 = append_last_month(RAW_DIR, S3_TABLE_URI)
    print(f"s3 append_last_month: {s3_rows1} rows")
