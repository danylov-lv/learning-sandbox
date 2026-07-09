# 05 — MinIO Object Store

## Backstory

The lake from task 04 lives on the single box you've been generating data on. That was fine for a side project; it is not fine for a team. Analysts on other machines can't reach `data/lake/`, there's no redundancy, and "just rsync it somewhere" is not a storage strategy. The plan is to move the lake onto an S3-compatible object store — MinIO here, but the same API as real S3 — so any machine with credentials and a network path can read it.

Object storage is not a networked filesystem, and treating it like one is where people get burned. There are no directories: `lake/month=2025-01/part-0.parquet` is one flat key, and "listing a directory" is actually a paginated `LIST` call capped at 1000 keys per page, walked page by page. There is no atomic rename: uploading a file means writing a new key, full stop. And every operation — every `PUT`, every `LIST` page, every `GET` — is a network round trip with its own latency, not a syscall. A dataset that was one `os.walk()` away from being enumerable on local disk becomes hundreds or thousands of individual HTTP requests once it's in a bucket, and how you write and read it now matters for a completely different reason than it did on local disk.

You already have two shapes of the same dataset from task 04: `data/lake/` (18 month partitions, ~18 files) and `data/lake-trap/` (~300 category partitions, thousands of tiny files). You're going to put both of them in the bucket and feel the difference LIST and per-request cost make on a small-files layout versus a sane one — a difference that barely registered on local disk.

## What's given

- `data/lake/` and `data/lake-trap/` from task 04, read-only.
- `data/ground-truth.json` from the module generator.
- MinIO already running: S3 API at `http://localhost:9301`, console at `http://localhost:9302` (`sandbox` / `sandbox123`), bucket `price-lake` already created. Endpoint and credentials are also available via `harness.common` (`minio_endpoint()`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`).
- `tests/bench.py` — uploads both dataset trees via your code, then measures LIST enumeration cost and query wall time against the bucket, local disk, and the small-files trap. Writes `05-minio-object-store/results-local.json`.
- `tests/validate.py` — the validator.

## What's required

Implement `src/upload_lake.py`: `upload(local_dir: Path, bucket: str, prefix: str) -> int`.

Walk `local_dir` recursively and upload every file to `bucket`, using the file's path relative to `local_dir`, joined onto `prefix`, as the object key — so `data/lake/month=2025-01/part-0.parquet` becomes the key `lake/month=2025-01/part-0.parquet` when called with `prefix="lake/"`. Return the number of objects uploaded.

Uploads must run concurrently, with a bounded worker pool. `data/lake-trap` has thousands of small files; uploading them one at a time, sequentially, waiting for each PUT's round trip before starting the next, is the exact mistake this task is designed to make painful. A bounded pool of worker threads issuing PUTs concurrently is the fix — and also a reasonable model of what a real upload tool does.

Then run:

```bash
uv run python 05-minio-object-store/tests/bench.py
uv run python 05-minio-object-store/tests/validate.py
```

Fill in `NOTES.md`: how many LIST pages did each prefix take to enumerate, and why does that track file count rather than data volume? How did the probe query's wall time against the S3 lake compare to the same probe against local disk, and to the same probe against the trap layout in the bucket? What would you change about the upload strategy if you were pushing terabytes instead of megabytes?

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- the `lake/` prefix in the bucket has exactly the 18 `month=YYYY-MM` prefixes implied by `ground-truth.json`'s `rows_by_month` keys, no extras, none missing;
- the object count under `lake/` equals the number of Parquet files in local `data/lake`;
- the total row count of the S3 `lake/` dataset equals `total_rows`, and a probe query (source + date-range filter from `filter_probe`, month-partition-pruned) against the S3 `lake/` dataset matches `filter_probe`'s row count and price sum (relative tolerance 1e-6);
- the object count under `lake-trap/` is at least 20x the object count under `lake/` — the same structural small-files signal task 04 used, now visible as object count instead of local file count;
- `results-local.json` exists and shows more LIST pages were needed to enumerate `lake-trap/` than `lake/`;
- `NOTES.md` filled in beyond the template.

## Estimated evenings

1-2

## Topics to read up on

- S3 API semantics: keys are flat, "directories" are a naming convention, `LIST` is paginated (max 1000 keys/page)
- Why S3-compatible stores have no atomic rename, and what that implies for how you write data safely
- Per-request latency and cost on object storage versus local filesystem syscalls
- Concurrent upload strategies: bounded thread/connection pools, and why unbounded concurrency against a single endpoint backfires
- `pyarrow.fs.S3FileSystem` and how `pyarrow.dataset` discovers a hive-partitioned dataset over S3 (partition pruning still works, but discovery now costs LIST calls)
- How the small-files problem compounds on object storage: each tiny file is now a full HTTP round trip, not just a syscall
