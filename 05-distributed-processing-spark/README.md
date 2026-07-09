# 05 — Distributed Processing (Spark)

## Backstory

PriceWatch's storage layer is solid now: partitioned Parquet, sane compression, a lake on MinIO with time travel. But the pipeline that fills that lake is still a single Python process reading JSONL off disk, and it has stopped keeping up. The scrapers are producing tens of millions of price-snapshot events a month, one source alone accounts for nearly a third of all traffic, retries duplicate rows, and a slice of every dump is simply broken (a timeout mid-write, a truncated line, a scraper that emitted `NOT_JSON` garbage instead of a snapshot). A single machine's RAM stops being the right way to think about this.

You are going to rebuild the processing layer on Spark: understand what "lazy evaluation" actually buys you and how to read a query plan before you run it, see partitions and shuffles happen instead of guessing about them, know when a join broadcasts and when it sorts-and-merges, understand why a Python UDF quietly kills throughput and what `pandas_udf` buys back, run window functions at a scale where the naive approach falls over, and land the result as a partitioned Parquet lake in object storage. Along the way you also learn when *not* to reach for Spark — the calibration task solves the same job in polars and makes you measure the crossover point yourself. The capstone is the real pipeline: raw scraped dumps in, a clean deduplicated partitioned lake out, with a shuffle-tuning pass measured in the Spark UI.

## Setup

Prerequisites: Docker with compose v2, uv, ~30 GB free disk for the default 50M-row dataset (raw JSONL plus derived Parquet copies the tasks produce).

```bash
cd 05-distributed-processing-spark
uv sync
docker compose up -d --wait
```

This starts two services:

- **MinIO** — S3-compatible object storage, API on `9501`, console on `9502` (user `sandbox`, password `sandbox123`). The bucket `price-lake-05` is created automatically by a `minio-init` sidecar.
- **spark** — a single `apache/spark:3.5.3-python3` container that idles (`sleep infinity`); you run jobs into it with `spark-submit` via the `run.sh` wrapper (see below). The Spark UI is exposed on `4040`, but it only serves pages while a job/SparkSession is actually running (local mode has no standalone master or history server in this setup — see "Spark UI" below).

Ports are overridable via `SANDBOX_05_MINIO_PORT` / `SANDBOX_05_MINIO_CONSOLE_PORT` / `SANDBOX_05_SPARK_UI_PORT`. These are deliberately distinct from module 04's MinIO ports (`9301`/`9302`) so both modules' compose stacks can run at once.

## Generate the dataset

```bash
uv run python generate.py                    # 50,000,000 valid rows (default)
uv run python generate.py --rows 2000000      # smaller run, e.g. the committed authoring test set
uv run python generate.py --gb 10             # size-targeted run instead of row-targeted
```

The generator is deterministic (fixed seed `50505`): the same arguments always reproduce byte-identical output — verified by hashing two independent `--rows 100000` runs. It writes:

- `data/raw-events/part-*.jsonl` — scraped price-snapshot events, one per line, with realistic mess:
  - **skewed source distribution**: source `1` gets ~30% of all rows, the other 19 sources split the rest zipf-style — this is the skew task-02 salts around;
  - **retry-storm duplicates**: ~3% of valid rows are byte-identical repeats of an earlier row in the same dump, injected at random positions (simulating a scraper that resent an unacknowledged request);
  - **malformed lines**: ~0.15% of emitted lines are not valid JSON at all (truncated objects, plain garbage text) — these load as `_corrupt_record` rows (or blow up a naive parser), which is the point;
  - nested `attrs` object, a null `price`/`in_stock` whenever `http_status != 200`, 18 months (2025-01 .. 2026-06) of seasonally- and diurnally-skewed timestamps.
- `data/reference/sources.csv` — 20 rows: `source_id, domain, name, region, default_currency, tier`. Small enough to be a textbook broadcast-join build side.
- `data/reference/categories.csv` — 240 rows: `category_id, category_path, vertical`.
- `data/ground-truth.json` — aggregates computed *during* generation, independent of any Spark code: `total_rows_raw` (valid JSON lines including duplicates), `exact_dupe_count`, `distinct_rows`, `malformed_line_count`, `rows_by_source`, `rows_by_month`, `price_sum_by_month`, a `filter_probe` (source + date range → row count and price sum), and `top_n_per_source` (top-3 prices per source among deduped `http_status==200` rows, for checking window-function ranking results). Task validators compare your output against this file, at any dataset scale.

Measured on the reference machine: `--rows 2000000` (the committed authoring test set) produces **2,000,000 valid rows / 2,060,000 raw lines incl. duplicates / 3,000 malformed lines, 979 MB, in 25 s** of generation plus a fixed ~6 s one-off universe/reference-table build. Generation is linear in row count past that fixed cost, so the default `--rows 50000000` run extrapolates to roughly **10.5 minutes and ~25 GB** on disk. The 2M-row authoring set is generated and kept in `data/raw-events/`, `data/reference/`, and `data/ground-truth.json` for task authoring and for running tasks without waiting ~10 minutes; regenerate at the full 50M scale when you actually want to feel Spark's shuffle behavior at size.

Cross-checked independently: reading the 2M-row set with `spark.read.json(...)` gives `total_lines = parsed_rows = 2,063,000`, with exactly `3,000` rows landing in `_corrupt_record` and `2,060,000` clean — matching `ground-truth.json`'s `total_rows_raw` and `malformed_line_count` exactly.

Everything under `data/` is gitignored (`**/data/` in the root `.gitignore`) and disposable. Regenerating is always safe, but any derived Parquet a task produced under `data/` must then be rebuilt too, since validators compare against the current `ground-truth.json`.

## How to work

Run all commands from this module directory (`05-distributed-processing-spark/`).

**The canonical way to run a Spark job** is the `run.sh` wrapper, which wraps `docker compose exec spark spark-submit` with the flags every task needs (local mode, a 6 GB driver heap, the s3a jars via `--packages` against a persistent ivy cache, and the MinIO endpoint/credentials):

```bash
./run.sh <path-relative-to-this-dir> [args...]
# e.g.
./run.sh 01-lazy-plans-and-explain/src/explore.py
```

Verified empirically on Windows + Git Bash: the script sets `MSYS_NO_PATHCONV=1` before the `docker compose exec` call so MSYS doesn't mangle the `/workspace/...` in-container path into a Windows path — without it the exec silently receives a garbled path. `--packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262` (matched to the Hadoop client bundled in `apache/spark:3.5.3-python3`) resolves against the `spark-ivy-cache` Docker volume mounted at `/opt/spark-ivy`; the first run downloads the jars, every run after that is served entirely from the cache (confirmed by running the same job twice back to back — identical wall time, no `downloading` log lines on the second run).

The container mounts the whole module directory at `/workspace`, so any file you write under a task's `src/` (or read from `data/`) is visible on the host immediately, and vice versa.

**Running task validators**: task validators that only read Parquet/CSV from the host filesystem run with `uv run` like any other module (`uv run python 0N-task/tests/validate.py`). Validators that need to inspect a live Spark query plan run *inside* the container the same way a job does — via `./run.sh 0N-task/tests/validate.py` — and use `harness/common.py`'s `get_plan(df)` / `plan_has(plan_text, pattern)` to capture and assert on `explain()` output (verified: a broadcast-hinted join produces a plan where `plan_has(plan, "BroadcastHashJoin")` is `True` and `plan_has(plan, "SortMergeJoin")` is `False`).

**Spark UI**: reachable at `http://localhost:4040` — but only while a `SparkSession` is alive. There is no standalone master and no history server here (deliberately: this module is local-mode-only, per the brief), so the UI is a live window into a running job, not a persistent dashboard. To read it: start a job with `./run.sh`, and while it's running (or in the few seconds it idles at the end if your script sleeps/pauses), open `localhost:4040` in a browser, or `curl -sL localhost:4040/` from another terminal — confirmed reachable this way (`HTTP 200`, page title `"<app-name> - Spark Jobs"`) during a live job.

**s3a / MinIO from inside Spark**: `spark.hadoop.fs.s3a.endpoint=http://minio:9000` (in-network hostname, not `localhost`), `spark.hadoop.fs.s3a.path.style.access=true`, `spark.hadoop.fs.s3a.access.key=sandbox`, `spark.hadoop.fs.s3a.secret.key=sandbox123`, `spark.hadoop.fs.s3a.connection.ssl.enabled=false` — all baked into `run.sh`. Read/write against `s3a://price-lake-05/...` — verified: a job wrote partitioned Parquet to `s3a://price-lake-05/smoke/counted` (partitioned by a string column) and read it back with matching row counts.

`.authoring/` contains generation notes with spoilers. Do not read it before finishing a task.

## Tasks

| # | Task | Evenings |
|---|------|----------|
| 01 | lazy-plans-and-explain — lazy evaluation, actions vs transformations, reading `explain()` | 1 |
| 02 | partitions-and-shuffles — partition count, `repartition` vs `coalesce`, skew + salting, Spark UI | 1-2 |
| 03 | joins-broadcast-vs-smj — broadcast vs sort-merge, AQE, plan-structure checks | 1-2 |
| 04 | udfs-and-arrow — python UDF vs `pandas_udf` vs built-ins, measured | 1 |
| 05 | windows-at-scale — window functions on 50M+ rows | 1-2 |
| 06 | parquet-to-minio-s3a — partitioned Parquet to object storage via s3a | 1 |
| 07 | polars-calibration — same job in polars vs Spark, when Spark is overkill | 1 |
| 08 | capstone-scrape-lake — raw dumps to clean partitioned lake + shuffle tuning (CP1/CP2/CP3) | 2-3 |

Tasks 01-05 build on the same `data/raw-events` dataset and increasingly touch the Spark UI. Task 06 needs MinIO up and is a prerequisite for the capstone's lake-writing step. Task 07 is a standalone calibration exercise (host-side, uv + polars, no Spark container needed) that reuses task 01-05's job shapes. The capstone (task 08) reuses everything: raw dumps → dedup/clean → join with `data/reference/` → partitioned Parquet lake on MinIO, with a shuffle-tuning pass you measure in the Spark UI.

## Teardown

```bash
docker compose down -v
rm -rf data/
```
