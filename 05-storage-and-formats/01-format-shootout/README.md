# 01 — Format Shootout

## Backstory

The scrapers write JSONL because it was the path of least resistance. The analysts import it into spreadsheets via CSV exports someone hand-rolls every week. Before you redesign anything, you need numbers: what does the same data actually cost in JSONL, CSV, and Parquet — in bytes on disk, in time to scan everything, and in time to read just one column? You will build the converters yourself, because the conversion is where all the real decisions hide (types, nulls, nested data, streaming).

## What's given

- `data/raw/part-*.jsonl` from the module generator, `data/ground-truth.json` next to it.
- `tests/bench.py` — a benchmark harness. It imports YOUR converters, runs them, then measures file sizes, full-scan time, and single-column-read time for each format, and writes `01-format-shootout/results-local.json`.
- `tests/validate.py` — the validator.

## What's required

Implement the two scaffolds in `src/`:

1. `src/convert_parquet.py` — `convert(raw_dir, out_path)`: all of `data/raw/*.jsonl` into a single Parquet file `data/formats/snapshots.parquet`.
2. `src/convert_csv.py` — `convert(raw_dir, out_path)`: the same rows into `data/formats/snapshots.csv`.

Contract (both converters):

- Columns, in this order: `product_id` (int64), `source_id` (int64), `url` (string), `title` (string), `category` (string), `brand` (string), `price` (float64, nullable), `currency` (string), `in_stock` (bool, nullable), `captured_at` (Parquet: `timestamp[us, tz=UTC]`; CSV: the ISO string as-is), `attrs` (string — the nested dict re-serialized as a JSON string), `scrape_run_id` (string), `http_status` (int64).
- Non-200 rows have `price` and `in_stock` null; they must stay null (empty field in CSV), not become `0` or `False`.
- Streaming: the process must never hold the whole dataset in memory. Keep peak RSS under ~4 GB regardless of dataset size. Chunked processing is the whole point — a `json.load`-everything one-liner is a fail even if it produces correct bytes.
- Return the number of rows written.

Then run the harness and the validator:

```bash
uv run python 01-format-shootout/tests/bench.py
uv run python 01-format-shootout/tests/validate.py
```

Record your measurements table and conclusions in `NOTES.md`: why is Parquet smaller than the JSONL it came from? Why does reading one column from CSV cost almost as much as reading all of it?

## Completion criteria

`tests/validate.py` prints PASSED. It checks:

- both output files exist and `results-local.json` has all measurements;
- correctness against `data/ground-truth.json`: row counts, per-currency counts, per-month price sums, distinct product count (from your Parquet), row count and total price sum (from your CSV);
- `captured_at` in Parquet is a UTC timestamp type, `price` nulls survived;
- relative targets (measured, machine-independent ratios): Parquet file size <= 35% of raw JSONL size; reading only the `price` column from Parquet is >= 5x faster than a full CSV scan.

## Estimated evenings

1-2

## Topics to read up on

- Row-oriented vs columnar storage layouts
- Parquet file anatomy: row groups, column chunks, pages
- Dictionary encoding and run-length encoding in Parquet
- pyarrow `ParquetWriter` and incremental writing
- Arrow type system: timestamps with timezones, nullable types
- Why CSV has no types and what that costs
