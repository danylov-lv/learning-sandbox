# 01 — Lazy Plans and `explain()`

## Backstory

You did this once already, in module 02, against Postgres: run `EXPLAIN`, read the plan tree, tell a seq scan from an index scan, tell a hash join from a nested loop, and use that to explain *why* a query is slow before touching any code. Spark asks the same question at a different scale, with a twist Postgres doesn't have: nothing runs until you call an action. `df.filter(...)` returns instantly no matter how big `df` is, because it hasn't touched a single row yet — it has only added a node to a plan. `df.count()` is what actually launches executors and moves data. Confusing "I wrote a transformation" with "I ran a job" is the single most common way people misjudge Spark's performance, and misdiagnose lazy pipelines as slow when the slow part hasn't even been reached yet.

PriceWatch's current ingestion script reads the raw scrape dumps with `json.loads` in a Python loop — every line is an action, whether you like it or not, because plain Python is eager. The whole point of moving to Spark is to build a pipeline once, lazily, and let the optimizer decide how to execute it. Before you can trust that, you need to see it happen: transformations that trigger nothing, actions that trigger exactly one job each, and a query plan that changes shape depending on what you asked for and what format you're reading from.

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` from the module generator (already present from the module-root `uv run python generate.py` run — see the module README if you need to regenerate).
- `src/explore.py` — a scaffold with five function signatures, each documented with its exact contract. All raise `NotImplementedError`.
- `harness/common.py` — `get_plan(df)` captures `df.explain("formatted")` as a string instead of printing it; `plan_has(plan_text, pattern)` checks a substring/regex against that string.
- `tests/validate.py` — the validator. It needs a live `SparkSession`, so it runs *inside* the container.

## What's required

Implement all five functions in `src/explore.py`:

1. **`job_counts_around_actions(spark)`** — prove, with numbers, that building transformations launches zero jobs and each action launches exactly one. Use `spark.sparkContext.statusTracker().getJobIdsForGroup()` to read how many jobs the application has run so far, at four checkpoints: after your source DataFrame exists (reading JSON without an explicit schema triggers its own schema-inference job — that's real, expected work, not the thing you're measuring, so your baseline is taken *after* the read, not before it), after adding transformations only, after a first action, after a second action.

2. **`narrow_vs_wide_plans(spark, jsonl_dir)`** — build one pipeline that only ever needs a narrow dependency (filter + select, no grouping/join/repartition) and one that needs a wide dependency (a `groupBy` aggregation). Return both plans as text via `get_plan`.

3. **`bootstrap_parquet_slice(spark, jsonl_dir, out_dir)`** — the one-time conversion step: read all raw JSONL, drop the unparseable lines, write the rest to Parquet at `out_dir`. This mirrors what task 06 will do properly (partitioned, to MinIO); here it's just enough Parquet to compare scan plans against.

4. **`pushdown_comparison(spark, jsonl_dir, parquet_dir)`** — run the *same* filter + column-selection query against the JSONL source and against the Parquet you just wrote. Return both plans. Read what actually differs before you assume you know.

5. **`dedup_filter_probe(spark, jsonl_dir)`** — the correctness check: read all raw JSONL, drop unparseable lines, deduplicate exact retry-storm repeats, filter to `source_id == 4` and `captured_at` in `[2025-09-01, 2025-10-31]` inclusive, and return the row count and price sum (over rows with `http_status == 200`) for that slice. This has to match `ground-truth.json`'s `filter_probe` exactly — it was computed independently, during generation, by counting canonical rows before duplication was injected.

Full docstrings with exact key names for every return value are in `src/explore.py` — the validator checks those keys literally.

Then run:

```bash
./run.sh 01-lazy-plans-and-explain/src/explore.py     # optional: add a __main__ block yourself to smoke-test locally
./run.sh 01-lazy-plans-and-explain/tests/validate.py
```

Fill in `NOTES.md`, including the module-02 parallel asked for there.

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `job_counts_around_actions`: zero new jobs between "source exists" and "transformations added"; exactly one new job per action after that.
- `narrow_vs_wide_plans`: the narrow plan's physical plan text does **not** contain `Exchange`; the wide plan's **does**.
- `bootstrap_parquet_slice`: the reported row count equals `ground-truth.json`'s `total_rows_raw` (all valid JSON lines, duplicates included — you only dropped the unparseable ones).
- `pushdown_comparison`: the Parquet plan's scan node says `Batched: true` and lists a non-empty `PushedFilters`; the JSONL plan's scan node says `Batched: false`. (Both may list `PushedFilters` — the JSON source reports which filters *could* apply, but only a columnar format can actually use them to skip work at scan time. `Batched` is the tell: it means the vectorized reader is active, which only Parquet supports here.) Both scans' `ReadSchema` must omit unrelated columns (e.g. `title`, `attrs`, `url`) you never selected — column pruning happens for both formats, it just doesn't buy Parquet anything extra on its own; it's `Batched` + real `PushedFilters` together that make Parquet cheaper to scan.
- `dedup_filter_probe`: row count and price sum match `ground-truth.json`'s `filter_probe` within a small floating-point tolerance.
- `NOTES.md` has real content, not just the template.

## Estimated evenings

1

## Topics to read up on

- Lazy evaluation: transformations vs actions in Spark's DataFrame API
- `SparkContext`/`SparkSession` job, stage, and task hierarchy
- Reading a Spark physical plan: `Scan`, `Filter`, `Project`, `Exchange`, `HashAggregate`
- Predicate pushdown and column pruning, and why they differ between row-oriented and columnar formats
- Vectorized (batched) columnar readers vs row-at-a-time readers
- Why deduplication needs whole-row equality and how that interacts with column pruning
