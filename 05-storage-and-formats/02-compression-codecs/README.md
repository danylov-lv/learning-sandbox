# 02 — Compression Codecs

## Backstory

Finance is asking why the Parquet lake still costs real money every month, and the analysts are asking why their ad-hoc queries feel slower than last quarter's spreadsheet export. Both complaints trace back to the same knob: compression codec. Snappy, gzip, and zstd sit at different points on the speed/ratio curve, and "just use the default" is not an answer finance or the analysts will accept. You need a hot-tier choice (analysts hit this data every day, read latency matters) and an archive-tier choice (written once, read rarely, storage cost dominates) — each backed by a number you measured yourself, not a blog post.

## What's given

- `data/raw/part-*.jsonl` and `data/ground-truth.json` from the module generator.
- `tests/bench.py` — writes all five variants via your code, times the write, then measures each variant's file size and full-scan read time. Produces `results-local.json`.
- `tests/validate.py` — the validator.

## What's required

Implement `src/write_codecs.py`: `write_all(raw_dir, out_dir) -> dict`.

Stream `data/raw/*.jsonl` and produce five Parquet files under `out_dir`, using the same 13-column schema as task 01 (`product_id`, `source_id`, `url`, `title`, `category`, `brand`, `price`, `currency`, `in_stock`, `captured_at`, `attrs`, `scrape_run_id`, `http_status` — see the scaffold docstring for exact types and null handling):

- `snapshots-none.parquet` — `compression="none"`
- `snapshots-snappy.parquet` — `compression="snappy"`
- `snapshots-gzip.parquet` — `compression="gzip"`
- `snapshots-zstd3.parquet` — `compression="zstd"`, `compression_level=3`
- `snapshots-zstd19.parquet` — `compression="zstd"`, `compression_level=19`

All five must contain the same rows. Whether you read the raw JSONL once and fan out to five open `ParquetWriter`s, or make five separate passes, is your design choice — both are legitimate and have different memory/time tradeoffs worth writing down. Streaming is mandatory either way: never hold the whole dataset in memory at once.

Return `{variant: rows_written}`.

Then run:

```bash
uv run python 02-compression-codecs/tests/bench.py
uv run python 02-compression-codecs/tests/validate.py
```

Fill in `NOTES.md`: which variant would you actually put in the hot tier, which in the archive tier, and why — cite your own size and read-time numbers. Also note what a single-pass-fan-out design costs you in peak memory versus a five-pass design, if you tried both, or reason about it if you only built one.

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- all five files exist, and each has `num_rows` equal to `ground-truth.json`'s `total_rows` (checked from Parquet footer metadata only — no full read);
- the `price` column's row-group-0 compression codec actually matches the variant (`none` → `UNCOMPRESSED`, `snappy` → `SNAPPY`, `gzip` → `GZIP`, `zstd3`/`zstd19` → `ZSTD`) — passing the wrong kwarg silently no-ops in some pyarrow versions, this check catches that;
- file size ordering: `none` is meaningfully bigger than `snappy`, `snappy` is meaningfully bigger than `zstd3`, `gzip` is meaningfully bigger than `zstd19` ("meaningfully" = more than a 2% difference, to avoid flip-flopping on near-ties);
- `results-local.json` has write and read timings for every variant;
- `NOTES.md` has real measurements and conclusions, not just the template.

## Estimated evenings

1

## Topics to read up on

- General-purpose compression families: LZ77-style dictionary matching vs entropy coding, and where snappy/gzip/zstd sit on that spectrum
- zstd compression levels and the speed/ratio tradeoff curve
- Parquet page-level compression vs file-level metadata
- Dictionary encoding in Parquet and how it interacts with (and sometimes reduces the value of) a general-purpose codec on top
