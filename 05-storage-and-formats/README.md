# Module 05 — Storage and Formats

## Backstory

Your PriceWatch scrapers dump everything they capture as JSONL: one price snapshot per line, straight from the spider to disk. It worked at 100 MB. Now the raw dumps are measured in tens of gigabytes per month, storage costs are climbing, and the analysts complain that answering "average price of category X last quarter" takes twenty minutes of full-file scanning. Nobody on the team has ever looked below the `pandas.read_csv` surface.

You are going to build the storage layer properly: columnar formats, compression, row-group anatomy, partitioning, an object store, a table format with time travel, and a query engine that exploits all of it. Every claim you make along the way must be backed by a measurement you ran yourself.

## Setup

Prerequisites: uv, Docker with Compose v2 for tasks 05–06, and about 15 GB of free disk for the default 5 GB dataset and its derived copies.

```bash
cd 05-storage-and-formats
uv sync
```

### Start MinIO for tasks 05 and 06

```bash
docker compose up -d --wait --build
docker compose run --rm minio-init
```

The first command builds MinIO and its CLI from pinned upstream releases. The second creates the `price-lake` bucket and is safe to rerun. The API and console are available locally on ports 9301 and 9302. The console at http://localhost:9302 uses `sandbox` / `sandbox123`. Override the host ports with `SANDBOX_04_MINIO_PORT` and `SANDBOX_04_MINIO_CONSOLE_PORT`, respectively.

## Generate the dataset

```bash
uv run python generate.py           # 5 GB of raw JSONL (default)
uv run python generate.py --gb 1    # smaller run
uv run python generate.py --rows 400000  # smaller dataset for the full exercise sequence
```

The generator is deterministic (fixed seeds): the same arguments always produce the same data. It writes:

- `data/raw/part-*.jsonl` — scraped price snapshots (product, source, messy unicode titles, nested `attrs` dict, skewed zipf/log-normal distributions, 18 months of timestamps with seasonal and diurnal skew, ~1.5% non-200 rows with null prices);
- `data/ground-truth.json` — aggregates computed while generating (row counts, per-currency counts, per-month price sums, distinct products, probe filters). Task validators check your outputs against this file. The structural checks assume enough rows to expose pruning and small-file effects, so use at least 400,000 rows for the full sequence.

Measured on the reference machine (NVMe SSD): `--gb 1` produces 1.0 GB / ~1.62 M rows in ~35 s (plus ~7 s one-off universe build); `--gb 5` extrapolates to roughly 8 M rows in ~3 minutes. Budget ~2x the raw size again for the Parquet/CSV/lake copies the tasks create under `data/`.

Everything under `data/` is gitignored and disposable. Regenerating is always safe, but note that derived artifacts (task outputs) must then be rebuilt too, since validators compare against the current `ground-truth.json`.

## How to work

- Run all commands from this module directory (`05-storage-and-formats/`), e.g. `uv run python 01-format-shootout/tests/validate.py`.
- Each task directory has `README.md` (the assignment), `src/` (scaffolds with TODOs — you write all the real code), `tests/` (validator and, where noted, a provided benchmark harness), `hints/` (three levels, escalating specificity), and `NOTES.md` (your measurements and conclusions — several validators check it is filled in).
- All performance targets are relative (ratios against baselines measured on your machine), never absolute times. Your absolute numbers will differ from anyone else's; the ratios should not.
- `.authoring/` contains generation notes with spoilers. Do not read it before finishing a task.

## Tasks

| # | Task | Evenings |
|---|------|----------|
| 01 | format-shootout — JSONL vs CSV vs Parquet, measured | 1-2 |
| 02 | compression-codecs — snappy / gzip / zstd across the hot-archive axis | 1 |
| 03 | row-groups-and-pushdown — row-group sizing, statistics, predicate pushdown | 1-2 |
| 04 | partitioned-datasets — hive partitioning and the cardinality trap | 1-2 |
| 05 | minio-object-store — the same lake on S3 API: latency and LIST cost | 1-2 |
| 06 | delta-lake — table format: appends, schema evolution, time travel, compaction | 2 |
| 07 | duckdb-taste — a query engine over your Parquet lake | 1 |
| 08 | capstone-lake-layout — design and build the 5-year, 10x-volume layout | 2-3 |

Tasks 01-04 build on each other's outputs (raw → parquet → sized row groups → partitioned lake). Task 05 needs MinIO up. Task 06 uses MinIO too. Task 07 reads task 04's partitioned lake. The capstone reuses everything.

## Teardown

```bash
docker compose down -v
rm -rf data/
```
