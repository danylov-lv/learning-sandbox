"""Write the same price-snapshot data five times, once per compression variant.

Reads every line of data/raw/*.jsonl and produces five Parquet files under
out_dir, all sharing the task-01 column contract:

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

Non-200 rows (http_status != 200) have price and in_stock null in the raw
JSON already — keep them null, do not coerce to 0 / False.

Variants, all written from the same logical rows:

    snapshots-none.parquet     compression="none"
    snapshots-snappy.parquet   compression="snappy"
    snapshots-gzip.parquet     compression="gzip"
    snapshots-zstd3.parquet    compression="zstd", compression_level=3
    snapshots-zstd19.parquet   compression="zstd", compression_level=19

Streaming requirement: never materialize the whole dataset in memory. Process
in bounded-size batches (a few tens of thousands of rows at a time is
reasonable). Whether you do one read pass writing all five files at once, or
one pass per variant, is your call — both are valid designs with different
time/memory tradeoffs, and that tradeoff is part of what NOTES.md should
discuss.
"""

from pathlib import Path


def write_all(raw_dir: Path, out_dir: Path) -> dict:
    """Convert data/raw/*.jsonl into the five compression-variant Parquet files.

    Args:
        raw_dir: directory containing part-*.jsonl input files.
        out_dir: directory to write the five snapshots-*.parquet files into
            (create it if it does not exist).

    Returns:
        dict mapping variant name ("none", "snappy", "gzip", "zstd3", "zstd19")
        to the number of rows written for that variant. All five counts must
        be equal (same rows, different codec).
    """
    raise NotImplementedError("implement write_all: stream raw_dir, write five compression variants to out_dir")
