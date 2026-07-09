# 07 — Polars Calibration

## Backstory

A week into the Spark rewrite, a teammate asks the uncomfortable question out loud: the monthly rollup job — dedupe, aggregate by month, a filtered slice, top-3-per-source — fits comfortably in RAM on one laptop. Did any of this actually need a cluster framework? You've been deep enough in `explain()` output and shuffle tuning that it's easy to forget the dataset in front of you is 2 million rows and under a gigabyte. Somewhere there's a size where Spark's local-mode JVM startup, container overhead, and shuffle bookkeeping stop being background noise and start being the point — and somewhere below that size, all of it is pure tax you're paying for a machine you're not using.

This task makes you find that line for yourself instead of taking it on faith. You reimplement the exact jobs from tasks 01-05 in polars against the same dataset, check your results against the same `ground-truth.json` those tasks' validators use, run a timed version of both stacks on your own machine, and write down what you actually saw — not what a blog post says you should see.

## What's given

- `data/raw-events/*.jsonl` and `data/ground-truth.json` (same dataset as tasks 01-05).
- `src/calibrate.py` — four function signatures, each with a full docstring contract, all raising `NotImplementedError`. The module docstring pins down a specific polars gotcha you'll hit immediately: `scan_ndjson`/`read_ndjson` do not have a "skip unparseable lines and keep going" option in polars 1.38.1 — `ignore_errors` only covers schema mismatches, not JSON syntax errors — so read that docstring before you write anything.
- `tests/bench.py` — **fully implemented, not yours to edit.** Two modes in one file: default (host, `uv run`) times your polars pipeline end-to-end; `--spark` (container, via `../run.sh`) times a small self-contained Spark twin of the same job. Both write into the same `results-local.json`; either half can be missing and the script tells you what to run next.
- `tests/validate.py` — the validator. Runs entirely on the host (no SparkSession needed — it only checks numbers).

## What's required

Implement all four functions in `src/calibrate.py`, working entirely through polars' lazy API (`pl.LazyFrame`, not eager `pl.DataFrame`, except where you must materialize to check something):

1. **`load_events(jsonl_dir)`** — a lazy frame of valid, deduplicated events. "Valid" means the ~3,000 syntactically-broken lines are gone; "deduplicated" means whole-row exact duplicates (the retry-storm repeats) are gone. Collecting it must land on exactly `ground-truth.json`'s `distinct_rows`.
2. **`monthly_rollup(lf)`** — row count and price sum per calendar month, matching `rows_by_month` / `price_sum_by_month` exactly (mind which rows count toward `rows` vs which count toward `price_sum` — they're not the same filter).
3. **`filter_probe(lf)`** — the same `source_id == 4`, `2025-09-01..2025-10-31` slice tasks 01/02 computed in Spark.
4. **`top3_per_source(lf)`** — top-3 prices per source, `http_status == 200` only, ties broken by `product_id` descending (this tie rule is documented in `ground-truth.json`'s `top_n_per_source.note` — read it, don't guess).

Then, from the module root:

```bash
uv run python 07-polars-calibration/tests/bench.py               # polars half, writes results-local.json
./run.sh 07-polars-calibration/tests/bench.py --spark             # spark half, appends to the same file
uv run python 07-polars-calibration/tests/validate.py             # the gate
```

Fill in `NOTES.md`. This task's deliverable is partly the writeup: a **Measurements** table with both wall-clock numbers, and a **Calibration memo** answering, in your own words and your own numbers, where the crossover is on your machine — dataset size, job shape, and per-job overhead all factor in — and where it stops being overkill: what changes at 50M rows? At 500M? When the input no longer fits on one disk, or one machine's RAM?

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `load_events` returns a `pl.LazyFrame` whose collected row count equals `ground-truth.json`'s `distinct_rows`.
- `monthly_rollup`'s `rows_by_month` matches exactly (int equality); `price_sum_by_month` matches within a small floating-point tolerance, for every month key.
- `filter_probe`'s `rows` matches exactly; `price_sum` matches within tolerance.
- `top3_per_source` matches `ground-truth.json`'s `top_n_per_source.by_source` **in order**, per source, for all 20 sources.
- `results-local.json` has both a `polars` and a `spark` entry, each with `wall_seconds > 0`. There is no ratio gate here — the point of this task is that you see the two numbers, not that one beats the other by some margin. `tests/bench.py` writes this file; don't hand-edit it.
- `NOTES.md` has real content, with a higher bar than usual — this task's deliverable is partly the writeup.

## Estimated evenings

1

## Topics to read up on

- Polars lazy evaluation (`LazyFrame`/`.collect()`) vs Spark's lazy DataFrame API — what "lazy" buys you when there's no cluster to schedule work across
- Predicate and projection pushdown in a single-node columnar query engine vs a distributed one
- Single-node columnar execution vs distributed shuffle: what a `groupBy` costs when it never leaves one process's memory
- Fixed overhead of a JVM + container + local-mode Spark session vs a native Rust/Arrow-backed engine starting cold
- Rule-of-thumb dataset-size boundaries for reaching for a cluster framework, and what actually changes at each order of magnitude (RAM-bound vs disk-bound vs genuinely can't-fit-on-one-box)
