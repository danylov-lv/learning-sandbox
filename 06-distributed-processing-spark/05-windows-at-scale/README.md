# 05 — Windows at Scale

## Backstory

PriceWatch's product managers want two things out of the clean event stream: a leaderboard of the top offers per source, and a per-product view of how price is moving over time. Both are window questions — "rank within a group" and "compare a row to the previous row in that group's ordering" — and at the row counts this pipeline runs at now, the difference between a window over a skewed partition key and a pre-aggregated equivalent of the same question stops being academic. Source `1` alone accounts for roughly 30% of all traffic; a window that partitions by `source_id` has to sort a partition thirty times the size of an average one on a single task, while a `groupBy` that only needs a running max never sorts anything at all. Reading a query plan is how you know which one you actually asked Spark to do.

This task is workable end to end on the committed 2M-row dataset, but it's designed to be felt at 50M+ rows — regenerate at scale (`uv run python generate.py`, see the module README) once your implementation passes, and watch `localhost:4040` while `top_n_per_source`'s DataFrame materializes. That's where "the naive approach falls over" stops being a phrase and starts being a Spark UI tab that takes a lot longer to finish than the other 19/20ths of the same job.

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` (same dataset as the other tasks in this module) — in particular `ground-truth.json`'s `top_n_per_source` block: the top-3 prices per source among deduplicated `http_status == 200` rows, ties broken by `product_id` descending, computed independently of any Spark code during data generation.
- `src/windows.py` — four function signatures, fully documented, all raising `NotImplementedError`.
- `harness/common.py` — `get_plan(df, mode)` captures a plan as a string; `plan_has(plan_text, pattern)` checks a substring/regex against it.
- `tests/validate.py` — the validator (runs in-container, needs a live SparkSession).

## What's required

Implement all four functions in `src/windows.py`:

1. **`prepare_events(spark, jsonl_dir)`** — the shared input: drop corrupt lines, deduplicate exact retry-storm repeats (whole-row `.distinct()`), no `http_status` filter here (each function below applies its own).
2. **`top_n_per_source(spark, events_df, n)`** — a window-ranked leaderboard: top `n` offers per `source_id` by price descending (ties broken by `product_id` descending), `http_status == 200` rows only. Must use a window function — the validator's plan check requires it. Getting the *values* right for every one of the 20 sources, in the exact order `ground-truth.json` records, means picking the ranking function that actually matches how the ground truth was built; the docstring in `src/windows.py` spells out why `row_number()`, `rank()`, and `dense_rank()` are not interchangeable here.
3. **`price_change_per_product(spark, events_df)`** — `lag()` over `partitionBy(product_id).orderBy(captured_at)`: each product's latest price against its previous snapshot, and the delta between them.
4. **`window_vs_aggregate_plans(spark, events_df)`** — the same question ("max price per source") answered two ways: a windowed top-1 (reusing the shape from #2) and a plain `groupBy(source_id).agg(max(price))`. Return both plans so the validator (and you) can see exactly what each shape costs — a `Window` node plus a full shuffle-and-sort in one, `HashAggregate` with no window node in the other.

Full docstrings with exact column-name and semantics contracts are in `src/windows.py`.

Then run (from the module root):

```bash
./run.sh 05-windows-at-scale/tests/validate.py
```

Fill in `NOTES.md`: the plan nodes you actually saw for each function, a few spot-checked top-3 rows against `ground-truth.json`, and your wall-time observations on the 2M-row set. If you regenerate at 50M+, note what changed — did `top_n_per_source` visibly take longer than `window_vs_aggregate_plans`'s aggregate branch? Did the Spark UI show one task in the window stage running far longer than its peers?

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `prepare_events` returns exactly the documented columns.
- `top_n_per_source`'s plan contains a `Window` node, and its output matches `ground-truth.json`'s `top_n_per_source.by_source` exactly — same prices, same product_ids, same order, exactly `n` rows per source — for all 20 sources.
- `price_change_per_product`'s output agrees with a reference the validator computes independently using only `groupBy`/`join` (no window function at all) — for every product, on every column, within a small float tolerance on price.
- `window_vs_aggregate_plans`'s `window_plan` contains a `Window` node and a shuffle/sort node (`Exchange` or `Sort`); its `aggregate_plan` contains no `Window` node; both formulations' per-source max prices agree with each other and with `ground-truth.json`.
- `NOTES.md` has real content, not just the template.

## Estimated evenings

1-2

## Topics to read up on

- Window function frame semantics: `rows between` vs `range between`, and why the default frame matters for `lag`/`lead` vs. aggregate-style window functions
- `rank()` vs `dense_rank()` vs `row_number()` — what each one does with ties, and why "top n" is a `row_number()` question, not a `rank()` question, unless you actually want tied rows to spill past n
- Partition skew inside a window: what it means for one `partitionBy` key's partition to dominate the others, and why the window's per-partition sort is where that skew actually bites
- `lag()`/`lead()` and the ordering column they depend on
- When a `groupBy` + `join` beats a window function for the same logical question, and when it can't (a window answering "give me every row's rank," not just the winner, has no groupBy-shaped equivalent)
- Reading a `Window` node and its neighboring `Exchange`/`Sort` nodes in a physical plan
