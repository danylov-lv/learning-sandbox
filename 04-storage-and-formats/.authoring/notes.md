# Authoring notes — 04-storage-and-formats

Generation-time notes for future authoring sessions. Contains spoilers
(reference numbers, reconciliation gotchas, decontamination history).
Learners are told not to read this file.

## Dataset

- Deterministic generator: `generate.py`, fixed seeds.
- Authoring/test set: 400k rows / 212 MB raw at `data/raw` — a single
  `part-0000.jsonl` because `ROWS_PER_FILE=1,000,000 > 400k`.
- Learner default: 5 GB.
- `ground-truth.json` keys: `total_rows`, `distinct_products`,
  `currency_counts`, `rows_by_month` (18 months, 2025-01..2026-06),
  `price_sum_by_month`, `filter_probe` (source_id=3,
  2025-09-01..2025-10-31, 114 rows, sum 4531.88 on the 400k set),
  `latest_price_probe` (10 products).
- All validator thresholds tuned on the 400k set with margin; they are
  relative/structural, so they hold at 5 GB too.

## Verification protocol (every task)

- Stock stub must fail cleanly: NOT PASSED, exit 1, no traceback.
- Pass-path proven with throwaway reference implementations kept in a
  session scratchpad, never committed.
- Shared state (MinIO bucket, `data/` derived dirs) restored to stock
  afterwards.

## 2026-07-09 decontamination note

Tasks 03, 04, 08 originally had throwaway reference implementations
accidentally committed in `src/` (03 also shipped `ref_common.py` and
lacked `NOTES.md`). Replaced with proper `NotImplementedError` stubs,
leftovers (`results-local.json`, `__pycache__`) removed, fail-paths
re-verified.

## Task 05 empirics (MinIO)

- On the 400k set: `data/lake` uploads as 18 objects (1 file/partition);
  `data/lake-trap` as ~2400 objects (~300 category dirs).
- LIST pages: 1 vs 3.
- Validator gates: exactly 18 `month=` prefixes; object count parity with
  local; trap >= 20x lake objects; trap LIST pages > lake LIST pages.
- Single-month aggregate: ~2.4s on s3 trap vs ~0.005s on s3 lake.

## Task 06 empirics (deltalake 1.6.0 / delta-rs)

- `append_last_month` splits the held-back last month into ~4000-row
  batches -> 6 append commits (design is dataset-size-robust; "one commit
  per raw part file" would give 1 commit on the 400k set).
- Streaming initial load via `RecordBatchReader` lands as exactly one
  commit.
- `history()` operationParameters `["mode"]` == `"Append"` (capitalized).
- `alter.add_columns` needs `deltalake.schema.Field`/`PrimitiveType`, not
  pyarrow types.
- `optimize.compact()` metrics keys are `numFilesAdded`/`numFilesRemoved`.
- `vacuum` needs `dry_run=False` + `enforce_retention_duration=False` +
  `retention_hours=0` to actually delete.
- MinIO S3 leg requires `storage_options`
  `AWS_ENDPOINT_URL`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/
  `AWS_ALLOW_HTTP=true`/`AWS_S3_ALLOW_UNSAFE_RENAME=true`; worked at full
  scale (s3 table version 6, 400k rows).
- `DeltaTable.schema().to_arrow()`, not `.to_pyarrow()`; no `.files()`
  method in this version.

## Task 07 empirics (duckdb 1.5.4)

- `filter_probe` reconciles ONLY with session `TimeZone=UTC` (harness runs
  `SET TimeZone='UTC'` before learner queries; default local tz silently
  shifted one boundary row: 113 rows / 4515.13).
- `price IS NULL` is exactly equivalent to `http_status != 200` in this
  data.
- `latest_price_probe` reconciles with `ROW_NUMBER() OVER (... captured_at
  DESC)` filtered to `price IS NOT NULL`.
- Pruning check runs the inner query of `pruning_proof.sql` under
  `PRAGMA enable_profiling='json'` and walks the plan JSON for
  `READ_PARQUET` `extra_info["Total Files Read"]` (2 pruned vs 18
  unpruned) — the boxed `EXPLAIN ANALYZE` text wraps mid-word and is
  unparseable.

## Cross-task contracts

- 13-column schema fixed in task 01: `product_id`, `source_id`, `url`,
  `title`, `category`, `brand`, `price` (nullable), `currency`,
  `in_stock` (nullable), `captured_at` (ts[us, UTC]), `attrs` (JSON-text),
  `scrape_run_id`, `http_status`.
- Outputs live under
  `data/{formats,codecs,rowgroups,lake,lake-trap,delta,capstone-lake}`.
- Learner results at `<task>/results-local.json` (gitignored via
  `**/*-local.json`).
- MinIO on ports 9301/9302, bucket `price-lake`, creds
  `sandbox`/`sandbox123`.
- `harness/common.py` is the single helper module for validators.
