# 06 — Parquet to MinIO (s3a)

## Backstory

Module 04 built the lake layout theory against local files: partitioned Parquet, sane compression, a directory structure a query engine can prune. Now that theory has to survive contact with a real object store. PriceWatch's actual lake lives in S3-compatible storage (MinIO here, S3 in production), reached from Spark through the `s3a://` filesystem connector, and object stores are not filesystems — there's no cheap atomic rename, "directories" are a naming convention over flat keys, and a naive write can leave you with hundreds of tiny files where you expected one per partition.

Your first attempt will probably do exactly that: `partitionBy("month")` with whatever partition count the read happened to produce, and you'll get a spray of small files scattered across each month's prefix. Then you'll fix it with a single, deliberate `repartition` before the write. And once the lake is written, you need to prove reading it back with a month filter actually *prunes* — that a query for one month touches one month's directory, not all eighteen.

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` (same dataset as tasks 01-05).
- MinIO, already running as part of this module's `docker compose up`, bucket `price-lake-05` already created and empty.
- `src/lake.py` — three function signatures, fully documented, all raising `NotImplementedError`.
- `tests/validate.py` — the validator. It runs inside the container (needs a live SparkSession and the s3a config `run.sh` wires up) and **does not write anything itself** — it only reads whatever your job already wrote.

This task namespaces all of its writes under `s3a://price-lake-05/task-06/` so it coexists with the capstone's future lake in the same bucket. Do not write outside that prefix.

## What's required

Implement all three functions in `src/lake.py`:

1. **`write_month_partitioned(spark, jsonl_dir, dest)`** — read the raw events, drop corrupt lines, deduplicate exact retry-storm repeats, derive a `month` column from `captured_at`, and write partitioned Parquet to `dest` with exactly one file per month partition. The docstring spells out why a plain `write.partitionBy("month")` does not give you that on its own, and what to add before the write so it does.

2. **`inspect_lake_files(spark, dest)`** — read the lake back and report, per month, how many distinct files sit under that month's directory, and whether every file path actually contains the `month=<value>` segment you'd expect.

3. **`pruned_read(spark, dest, month)`** — read the lake filtered to a single month and prove, two different ways, that pruning happened: the captured physical plan must show the scan itself doing the filtering (not a `Filter` node downstream of an unfiltered scan), and a runtime check (`input_file_name()`) must show only that one month's file was actually opened.

Full docstrings with exact return-value keys are in `src/lake.py` — the validator checks those keys literally.

### Running your job

Unlike earlier tasks, `tests/validate.py` here never writes to the lake — it only validates whatever is already sitting at the fixed path `s3a://price-lake-05/task-06/lake`. You need a separate way to actually run `write_month_partitioned` against that path. The simplest option, following the same pattern task 01's README suggests for `src/explore.py`: add a `__main__` block to the bottom of `src/lake.py` yourself that builds a `SparkSession`, calls your function with `dest="s3a://price-lake-05/task-06/lake"`, and prints the result. Then:

```bash
./run.sh 06-parquet-to-minio-s3a/src/lake.py        # your write job — writes the lake
./run.sh 06-parquet-to-minio-s3a/tests/validate.py  # the actual gate — only reads
```

Before you settle on the controlled write, it's worth deliberately observing the naive spray: write once to a *different* scratch prefix (e.g. `s3a://price-lake-05/task-06/naive`) with `partitionBy("month")` but no `repartition("month")` first, count the files per partition (`mc ls` against MinIO, or the same `input_file_name()` trick you'll use in `inspect_lake_files`), then clean that prefix up before moving on — it isn't part of what the validator checks, and the bucket is shared with a future capstone task. Record what you saw in `NOTES.md`.

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks, entirely by reading `s3a://price-lake-05/task-06/lake`:

- If nothing is there yet, it fails cleanly telling you to run your write job first — it does not write the lake for you.
- Per-month row counts read back from the lake match `ground-truth.json`'s `rows_by_month` exactly, for all 18 months, and the total matches `distinct_rows`.
- `inspect_lake_files` reports exactly 1 file per month partition, and every file path contains its own `month=` directory segment.
- `pruned_read` for a fixed probe month: the captured plan's scan node shows a non-empty `PartitionFilters` mentioning `month`; the row count matches ground truth for that month; and only 1 distinct file was touched at read time.
- `NOTES.md` has real content, not just the template.

## Estimated evenings

1

## Topics to read up on

- s3a committers and why object stores have no cheap atomic rename
- `partitionBy` directory layout (`month=YYYY-MM`) vs how many files land in each directory
- Partition pruning vs predicate pushdown — related but distinct optimizations, and how to tell which one a plan shows you
- The small-files problem in object storage lakes, and why it matters more there than on a local filesystem
- `repartition` before a partitioned write, and why the column you repartition by should match the column you partition by
- Path-style vs virtual-hosted-style S3 addressing, and endpoint/credential configuration for S3-compatible stores that aren't AWS
