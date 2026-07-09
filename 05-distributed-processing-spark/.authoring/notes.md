# Module 05 authoring notes — SPOILERS

Learner: do not read this before finishing the module's tasks. It documents design
intent and validator internals.

## Dataset and ground-truth semantics (generate.py, seed 50505)

- Committed authoring set: `--rows 2000000` → 2,063,000 lines = 2,060,000 valid
  JSON (60,000 exact whole-row duplicate lines, 2,000,000 distinct) + 3,000
  malformed lines. Determinism verified by hashing two independent runs.
- Dedup everywhere means whole-row byte equality (retry-storm rows are literal
  re-inserted copies), never key-based.
- `rows_by_month` / `rows_by_source`: deduped rows, all `http_status` values.
- `price_sum_by_month` and `filter_probe.price_sum`: `http_status == 200` only.
- `filter_probe`: half-open window `["2025-09-01", "2025-11-01")` via ISO-string
  comparison, source 4.
- `top_n_per_source`: deduped `http_status == 200` rows, top 3 by price DESC,
  ties by product_id DESC, over raw rows (not per-product — source 1's list has
  product 151512 twice at different prices). Matches `row_number()` semantics
  exactly; `rank()`/`dense_rank()` spill tied-boundary rows past n.

## Spark 3.5.3 empirics the validators rely on

- `explain()` only prints; `harness.common.get_plan()` captures via stdout
  redirect (drives the same QueryExecution.explainString path).
- With AQE on, an un-executed adaptive plan reports `rdd.getNumPartitions() == 1`
  and shows `AdaptiveSparkPlan isFinalPlan=false`; tasks that count partitions or
  inspect static plans must disable AQE first (tasks 01/02 contracts do).
- Session config leaks across calls sharing one SparkSession: task 03's
  `force_sort_merge` sets `autoBroadcastJoinThreshold=-1`, and
  `aqe_converts_join` called after it never converts unless the threshold is
  reset to the default 10485760. Documented in stubs and hint-2.
- AQE SMJ→broadcast runtime conversion reproduces reliably with per-product
  monthly aggregates (Nov vs Dec 2025) joined on `product_id`, AQE on, default
  threshold: pre-action plan `isFinalPlan=false` + SortMergeJoin, post-action
  `isFinalPlan=true` with BroadcastHashJoin in the `== Final Plan ==` section.
  The formatted output retains the Initial Plan (still shows SortMergeJoin), so
  task 03's validator slices out the Final Plan section instead of substring
  matching the whole text.
- UDF plan nodes: plain `F.udf` → `BatchEvalPython`; `pandas_udf` →
  `ArrowEvalPython`; built-ins → neither. Measured at 2M rows (noop-write sink,
  cache-warmed): python 5.9–10.2 s, pandas 2.9–4.9 s, builtins ~0.8 s. Task 04
  gates python/builtin >= 3.0 and python/pandas >= 1.3 (observed floors ~7x and
  ~1.9x — generous slack).
- `df.write.format("noop").mode("overwrite").save()` is the clean timing sink
  (full materialization, no driver collection).
- Window plans: `Window` node plus Exchange/Sort; the groupBy+join equivalent
  has no `Window` node — task 05's plan gate.
- Partitioned Parquet scan on s3a: the pruning gate is a non-empty
  `PartitionFilters: [... (month = YYYY-MM)]` on the scan node. In `formatted`
  mode `PushedFilters` does not appear at all when the whole predicate is
  satisfied by pruning (it shows as `PushedFilters: []` only in `simple` mode) —
  noted in task 06 hint-3 to avoid confusion. Runtime cross-check: distinct
  `input_file_name()` under the filter.
- Naive `partitionBy("month")` without a prior `repartition("month")` sprays
  one file per (input partition x month); repartition-by-partition-column first
  gives exactly 1 file per partition. Dedup + month-partitioned write of the 2M
  set to MinIO via s3a: ~34 s.
- Broadcast enrich of both reference tables (20-row sources, 240-row
  categories): two BroadcastHashJoin nodes, zero SortMergeJoin; inner join on
  `category_id` preserves all rows (verified, categories.csv covers 1..240).
  Task 03's validator derives expected per-region counts from
  `ground-truth.rows_by_source` + `sources.csv` in pure Python:
  uk=1424071, us=467157, eu=49144, apac=59628 at the 2M scale.

## Capstone (task 08) empirics

- Whether a `groupBy().agg()` result auto-broadcasts without an explicit hint
  depends on unrelated factors: a cached upstream read gives inaccurate stats
  (stays SortMergeJoin) while a fresh Parquet read's footer stats let it
  auto-broadcast even with AQE off. Never gate a validator on that heuristic;
  force `autoBroadcastJoinThreshold=-1` for the naive side (as task 03 does).
- Formatted-plan node-name occurrences are doubled (tree summary + detail
  section), so gates check presence/thresholds, not exact counts.
- CP2 job (month-over-month avg-price delta per product/source, rolled up by
  region): naive (threshold -1, AQE off, 200 shuffle partitions) 2.8–3.3 s vs
  tuned (AQE on, explicit broadcast of the region dim, shuffle.partitions=8)
  0.66–0.84 s at 2M rows; timing gate `tuned <= 0.9 x naive` with the
  structural plan gate as primary.
- DESIGN.md fill-in templates must be measured against their own
  `check_notes_filled` threshold: the first draft template scored 1806 chars
  against a 1200 gate (would have passed empty); final template ~950 chars
  with a 1500 gate.

## polars 1.38.1 empirics (task 07)

- `scan_ndjson` / `read_ndjson` raise `ComputeError` on syntactically-malformed
  JSON lines; `ignore_errors=True` only tolerates schema mismatches. The
  workable approach is a byte-level structural prefilter of lines before
  handing survivors to the lazy scan (drops exactly the 3,000 bad lines, <1 s).
- Calibration data point on the reference machine, 2M rows: polars full rollup
  13.2 s vs the Spark twin 34.4 s — Spark overhead dominates at this scale,
  which is the task's intended conclusion.

## NOTES.md gate calibration

- `check_notes_filled` default is 200 chars of non-template content. Keep
  unfilled templates near ~150 chars (tasks 02–08 do). Task 01's template alone
  scores 441 (pre-filled ground-truth table rows + the Postgres-parallel
  prompt), so its validator was bumped to `min_chars=650` during this session.
- Task 07 deliberately uses `min_chars=700` (the calibration memo is part of
  the deliverable); its unfilled template scores 397.

## Verification status

- Tasks 01–08 (capstone cp1/cp2/cp3 included): validators verified live on the
  2M set — stock stubs fail
  cleanly (`NOT PASSED`, exit 1, no tracebacks), pass paths proven with
  throwaway reference implementations in a gitignored `scratch/` dir, stubs
  restored byte-identical afterward, `scratch/` removed. No reference solutions
  committed anywhere. MinIO bucket left empty; `data/` left at stock
  (raw-events + reference + ground-truth.json).
- Root-level `probe_*.py` scripts from the foundation session were folded into
  these notes and deleted.
