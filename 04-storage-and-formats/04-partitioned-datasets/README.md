# 04 — Partitioned Datasets

## Backstory

The analysts never ask "give me everything." Every query they actually run is
scoped to a month, or a month and a source: "average price in source 3 during
September and October," "total GMV for November." Right now that means
scanning all 18 months of Parquet every single time, because task 01/03's
single file (or unsorted row groups) has no idea which rows belong to which
month without opening them and checking.

Partitioning fixes this — split the dataset into directories keyed by the
column analysts actually filter on, so a month-scoped query only opens the
files it needs. But partitioning is also a loaded gun: pick a partition key
with too many distinct values and you get an explosion of tiny files, one
directory per value, most of them a few KB, and now every query pays for
opening thousands of file handles instead of scanning bytes. You are going to
build the correct layout, then deliberately build the wrong one, and measure
both.

## What's given

- `data/raw/part-*.jsonl` and `data/ground-truth.json` from the module
  generator (see the module README for how to (re)generate).
- `src/build_lake.py`, `src/build_trap.py` — scaffolds with the full contract
  in their docstrings.
- `tests/bench.py` — builds both layouts by calling your `build()` functions,
  measures file counts, median file size, probe-query wall time and files
  touched, and single-month aggregate wall time, for both layouts. Writes
  `04-partitioned-datasets/results-local.json`.
- `tests/validate.py` — the validator.

## What's required

Implement:

1. `src/build_lake.py` — `build(raw_dir, lake_dir) -> int`. Hive-partitioned
   Parquet dataset at `data/lake/month=YYYY-MM/part-*.parquet`, month derived
   from `captured_at` (UTC). zstd level 3. Same 13 columns as task 01's
   contract (see the scaffold docstring for the exact list/types). Within
   each partition, rows sorted by `(source_id, captured_at)`. Each partition
   ends up as a small number of files — not hundreds. Streaming, bounded
   memory. Returns total rows written.

2. `src/build_trap.py` — `build(raw_dir, trap_dir) -> int`. The same rows,
   partitioned by `category` instead, at
   `data/lake-trap/category=<path>/part-*.parquet`. `category` is the row's
   full 3-level path (e.g. `"electronics/mid/leaf"`), a single string column
   — do not split it. **Measured cardinality: 300 distinct values** in the
   reference 400k-row dataset (`brand` was checked first and rejected — it
   only has 120 distinct values in this data, not enough for the file-count
   explosion to be dramatic; `category` was the column with several hundred
   distinct values). Verify this against your own `data/raw` before
   committing to it — if you regenerated with different settings and the
   cardinality looks too low, say so in your `NOTES.md` and pick a different
   column. No sorting requirement, no file-count control — write it the
   naive way, streaming chunk by chunk straight into a partitioned writer,
   the way someone reaches for `write_dataset` without thinking about it.

Run:

```bash
uv run python 04-partitioned-datasets/tests/bench.py
uv run python 04-partitioned-datasets/tests/validate.py
```

Record your measurements and conclusions in `NOTES.md`: how many files did
each layout produce, and why? How much faster was the probe query against
the month layout, and how many fragments did it actually touch versus the
total? What happened to the single-month aggregate against the trap layout,
and why does partitioning by `category` not help it at all?

## Completion criteria

`tests/validate.py` prints PASSED. It checks:

- `data/lake` has exactly the 18 `month=YYYY-MM` partition directories implied
  by `ground-truth.json`'s `rows_by_month` keys — no extras, none missing;
- per-partition row counts (read from Parquet file metadata, not a full data
  read) match `rows_by_month`; total rows match `total_rows`;
- per-month price sums (via a dataset scan) match `price_sum_by_month`
  (relative tolerance 1e-6);
- rows inside every `data/lake` partition file are sorted by
  `(source_id, captured_at)`;
- a structural pruning check: querying `data/lake` with `month` restricted to
  the two months covered by `ground-truth.json`'s `filter_probe` date range
  touches only the fragments physically inside those two partition
  directories, not all 18;
- the probe query's actual result (row count, price sum) against `data/lake`
  matches `filter_probe` (relative tolerance 1e-6);
- `data/lake-trap` exists with at least 200 `category=...` partition
  directories, and its total file count is at least 20x `data/lake`'s total
  file count;
- `NOTES.md` filled in beyond the template.

## Estimated evenings

1-2

## Topics to read up on

- Hive-style partitioning (directory-encoded partition columns)
- Partition pruning vs row-group pruning vs page-level statistics pruning
- The small-files problem in columnar lakes
- Write amplification from over-partitioning
- Dataset discovery cost (listing thousands of directories before a query
  even starts)
- Choosing a partition key: cardinality vs query shape
