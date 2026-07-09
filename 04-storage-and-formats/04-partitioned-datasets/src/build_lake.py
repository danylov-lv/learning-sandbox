"""Build the correctly-partitioned lake: hive-partitioned by month.

Contract
--------
    build(raw_dir, lake_dir) -> int

- `raw_dir`: directory containing `part-*.jsonl` (task-01 row schema).
- `lake_dir`: directory to write into, e.g. `data/lake`. Safe to call
  more than once — replace previous output, do not append to it.

Produce a hive-partitioned Parquet dataset at:

    lake_dir/month=YYYY-MM/part-*.parquet

`month` is derived from `captured_at` (UTC), e.g. a row with
`captured_at = 2024-03-17T...Z` belongs to partition `month=2024-03`.

Each file uses the task-01 13-column schema, in this exact order and type:

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
    attrs           string  (the nested `attrs` dict re-serialized as JSON text)
    scrape_run_id   string
    http_status     int64

Non-200 rows carry `price: null` / `in_stock: null` in the source data —
preserve those as nulls, never coerce to 0 / False.

Requirements
------------
- Compression: zstd, level 3.
- Sort: within each partition, rows sorted by `(source_id, captured_at)`.
  If a partition ends up split across more than one file, each file must
  be internally sorted by this key (a reader prunes by the file it opens,
  not by some global order that doesn't survive the split).
- File count: each partition should end up as a small number of files —
  not hundreds. Bound this with a rows-per-flush threshold, not by
  loading a whole partition's rows unboundedly before writing.
- Streaming, bounded memory: never materialize the whole dataset (or a
  whole month, if a month is very large) in memory at once. There are
  only 18 distinct month keys in this dataset — a per-month in-memory
  buffer with a flush threshold, kept open for the whole streaming pass,
  is a reasonable approach.

Returns
-------
Total number of rows written across all partitions.
"""


def build(raw_dir, lake_dir):
    raise NotImplementedError(
        "implement build: stream raw_dir, write a month-partitioned, sorted, zstd lake to lake_dir"
    )
