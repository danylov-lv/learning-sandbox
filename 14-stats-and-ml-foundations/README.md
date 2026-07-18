# 14 — Stats and ML Foundations

## What this module covers

You can write a scraper and land data in a table. This module trains what
comes after: can you trust the numbers you just landed, and can you say
something defensible about them? All 13 tasks share one dataset — a
realistic "scraped product-price" corpus with planted data-quality defects,
a genuine outlier tail, and a confound designed to fool a naive correlation
read. Three arcs:

- **Arc A — numpy/pandas/viz fundamentals.** Vectorized array thinking,
  exploratory data analysis over the shared dataset, and matplotlib well
  enough to make a defensible chart.
- **Arc B — applied statistics (the core of this module).** Why real price
  data isn't normal, telling a genuine outlier from a parsing error,
  confidence intervals, the bootstrap, A/B testing two scraping strategies,
  and correlation vs. causation on a dataset built to have a Simpson's-
  paradox-flavored confound.
- **Arc C — a shallow, honest tour of ML.** sklearn pipeline leakage,
  feature engineering, PyTorch tensors and autograd from first principles,
  capped by a text-classification capstone (predict category from title).

The goal is statistical and ML literacy sufficient to reason about a data
pipeline's outputs — not to become an ML engineer.

There are **no docker services** in this module — it is pure Python.
Everything runs against a parquet file generated once on your machine.

## Running

```bash
cd 14-stats-and-ml-foundations
uv sync
uv run python generate.py               # builds data/observations.parquet + ground-truth.json
uv run python NN-task-name/tests/validate.py
```

`generate.py` is deterministic (fixed seed, respects `SCALE`, default `1.0`
= 60000 observations) and writes `data/observations.parquet` (gitignored)
plus the committed `data/ground-truth.json` several tasks grade against.
`SCALE=0.05 uv run python generate.py` gives a fast ~3000-row smoke run.
`GROUND_TRUTH_ONLY=1 uv run python generate.py` recomputes only the answer
key, skipping the parquet write.

Every task imports shared plumbing from `harness/common.py`: pass/fail
helpers, `load_observations()` / `load_ground_truth()`, float-tolerant
comparison (`approx` / `check_close` — never exact-decimal equality on
money), a structural plot check (`require_figure`), and the relative-timing
baseline helpers (`time_it` / `write_baseline` / `read_baseline`).
Validators print `PASSED` or `NOT PASSED: <reason>` and never leak a raw
traceback.

## Tasks

| # | Task | Status |
|---|------|--------|
| 01 | vectorization-and-broadcasting | pending |
| 02 | eda-scraped-prices | pending |
| 03 | matplotlib-fundamentals | pending |
| 04 | price-distributions-not-normal | pending |
| 05 | outliers-vs-parsing-errors | pending |
| 06 | confidence-intervals | pending |
| 07 | bootstrap | pending |
| 08 | ab-test-scraping-strategies | pending |
| 09 | correlation-vs-causation | pending |
| 10 | sklearn-pipeline-leakage | pending |
| 11 | feature-engineering | pending |
| 12 | pytorch-tensors-autograd | pending |
| 13 | capstone-text-classifier | pending |

## Verification philosophy

- **Stats tasks** (Arc B): validators check numeric answers against
  `load_ground_truth()` or a validator-recomputed reference within a float
  tolerance, plus a structural check (`require_figure`) that a required plot
  was actually drawn. Visual correctness itself is human-checked — the
  validator can't judge whether your histogram is well-labeled, only that
  one exists and has content.
- **ML tasks** (Arc C): metric thresholds evaluated on a held-out split with
  a fixed split seed, so the learner's split and the validator's split agree.
- **Timing tasks**: relative to a machine-local baseline only, via
  `write_baseline` / `read_baseline` — never an absolute wall-clock number.

## `.authoring/` is off-limits until after a task

`.authoring/` holds spoilers: the full harness API contract, the dataset
schema and exact RNG draw order, the defect-planting and confound
construction, and the committed ground-truth values. Read it *after*
finishing a task, never before.
