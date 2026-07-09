# 03 — Joins: Broadcast vs Sort-Merge

## Backstory

PriceWatch's raw events are just numbers until they're attached to meaning: `source_id` needs to become a domain and a region, `category_id` needs to become a vertical you can report on. Both lookup tables are tiny — 20 rows, 240 rows — so joining them to millions of events should never cost a shuffle of the event side. It doesn't, if you tell Spark what you already know: broadcast the small side, skip the sort-and-shuffle entirely.

Not every join gets that luxury. The next question on the roadmap — "did this product's price move month over month?" — needs two aggregates built from the *same* large table, one per month, joined to each other. Neither side is obviously tiny. Left to its own devices, Spark's planner falls back to a sort-merge join: shuffle both sides by key, sort each partition, walk them in lockstep. That's correct and it's the right default when both sides are genuinely large — but it's also where Adaptive Query Execution (AQE) earns its keep: it watches the actual size of each side *after* the shuffle and can rewrite a sort-merge join into a broadcast join at runtime, if it turns out one side collapsed down to something small once aggregated.

This task makes you produce all three shapes — broadcast-forced, sort-merge-forced, and AQE's own runtime call — and prove which one happened by reading the plan, not by guessing from timing.

## What's given

- `data/raw-events/*.jsonl`, `data/reference/sources.csv`, `data/reference/categories.csv`, and `data/ground-truth.json` (same dataset as tasks 01 and 02).
- `src/joins.py` — three function signatures, fully documented, all raising `NotImplementedError`.
- `harness/common.py` — `get_plan(df, mode)` captures a plan as a string; `plan_has(plan_text, pattern)` checks a substring/regex against it.
- `tests/validate.py` — the validator (runs in-container, needs a live SparkSession).

## What's required

Implement all three functions in `src/joins.py`:

1. **`broadcast_enrich(spark, jsonl_dir, reference_dir)`** — deduplicate the raw events (drop `_corrupt_record` rows, whole-row `.distinct()`), then join to `sources.csv` on `source_id` and to `categories.csv` on `category_id`, forcing both joins to broadcast the reference side. Report the joined plan and two grouped row counts: by `region` and by `vertical`.

2. **`force_sort_merge(spark, jsonl_dir)`** — with AQE off and `spark.sql.autoBroadcastJoinThreshold` set to `-1`, build per-`(product_id, source_id)` monthly aggregates for two different months and inner-join them. Neither aggregated side is trivially small, and broadcasting is disabled outright, so the planner has no path except sort-merge. Also build a broadcast-hinted twin of the same join (a hint overrides the `-1` threshold) and confirm both return the same row count.

3. **`aqe_converts_join(spark, jsonl_dir)`** — with AQE on and the default broadcast threshold, build a smaller pair of monthly aggregates (per `product_id` alone) and inner-join them. Capture the plan *before* calling any action — the static planner picks sort-merge here too, because at plan-build time it doesn't know either side turned out small. Then materialize the join and capture the plan again on the same DataFrame: AQE's adopted "Final Plan" now uses a broadcast join, because it measured the real post-aggregation size at runtime.

Full docstrings with exact key names are in `src/joins.py` — the validator checks those keys literally.

Then run:

```bash
./run.sh 03-joins-broadcast-vs-smj/tests/validate.py
```

Fill in `NOTES.md`: which plan nodes you actually saw for each function, the row counts, and what specifically changed between the pre-action and post-action plan capture in `aqe_converts_join`.

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `broadcast_enrich`: the plan contains at least two `BroadcastHashJoin` occurrences and no `SortMergeJoin`; `deduped_row_count` equals `ground-truth.json`'s `distinct_rows`; `rows_by_region` matches a count derived independently (in the validator, no Spark involved) from `ground-truth.json`'s `rows_by_source` combined with `sources.csv`'s `source_id → region` mapping; `rows_by_vertical`'s values sum to `distinct_rows` (every event's `category_id` must join to exactly one row of `categories.csv` — an inner join that drops nothing).
- `force_sort_merge`: the plan contains `SortMergeJoin` and no `BroadcastHashJoin`; `row_count` is positive and equals `broadcast_row_count` (the broadcast-hinted twin) — the join strategy must never change the result.
- `aqe_converts_join`: `plan_before_action` shows `isFinalPlan=false`; `plan_after_action` shows `isFinalPlan=true` and its `== Final Plan ==` section contains `BroadcastHashJoin` — proof that AQE rewrote the join strategy at runtime, not at plan-build time.
- `NOTES.md` has real content, not just the template.

## Estimated evenings

1-2

## Topics to read up on

- Broadcast hash join vs sort-merge join: when each is chosen and why
- `spark.sql.autoBroadcastJoinThreshold` and the `broadcast()` DataFrame hint
- Adaptive Query Execution (AQE): runtime statistics, `AdaptiveSparkPlan`, `isFinalPlan`
- Reading an AQE-formatted plan's `== Initial Plan ==` vs `== Final Plan ==` sections
- Why join strategy never changes a join's result, only how it's computed
- Inner join cardinality: when a join is guaranteed not to drop or duplicate rows
