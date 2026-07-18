# 02 -- EDA Scraped Prices

## Backstory

You inherited a fresh scraped dump -- 60,000 rows of product prices,
categories, and metadata, pulled off three source sites over the last 90
days. Nobody on the team has looked at it closely yet. Before you trust any
downstream number that gets computed from this table -- a median price by
category, a "how much did prices move" comparison, a chart in someone's
deck -- your first job is to actually know your data: how big is it, how is
it split up, how much of it is missing or broken, and does a plain-language
description of a "typical row" match what a domain expert would expect.
Skipping this step is how a dropped-decimal parsing bug or a silently
un-normalized currency column ends up baked into a report three steps
downstream, discovered only when someone asks why the average electronics
price is $50,000.

This task is also where you build a habit worth keeping: computing an
answer once is a claim, computing it twice in two different tools and
getting the same number is evidence. You'll do every fact in this task
twice -- once in pandas, once in polars -- and confirm they agree before
trusting either one.

## What's given

- `src/eda.py` -- the scaffold you implement. Three functions, each with a
  rich docstring spelling out the exact contract: `summarize_pandas(df)`,
  `summarize_polars()`, and `make_figure(df)`. Read the module docstring
  first -- it defines the fixed set of EDA facts you need to compute and,
  critically, the exact "valid price" definition this task uses (spelled
  out precisely so your answer and the validator's grading agree on what
  counts as a valid row).
- The shared dataset at `data/observations.parquet` (already generated --
  if it's missing, run `uv run python generate.py` from the module root
  first), loadable via `harness.common.load_observations()` (pandas) or
  directly via `polars.read_parquet(harness.common.OBSERVATIONS_PATH)`.
- `harness/common.py` at the module root: `load_observations`,
  `load_ground_truth`, `check_close`, `require_figure`, and the
  `guarded`/`not_passed`/`passed` pass-fail plumbing every validator in this
  module shares.

## What's required

1. `summarize_pandas(df: pandas.DataFrame) -> dict` -- compute the fixed
   set of EDA facts (row count, distinct product count, per-category row
   counts, valid-price median/mean, the NaN-price rate, per-source-site row
   counts, and the busiest scrape day) using pandas. The exact dict shape
   and the "valid price" definition are documented in `src/eda.py`'s module
   docstring -- read it before writing any aggregate.
2. `summarize_polars() -> dict` -- the SAME facts, computed independently
   with polars, reading the parquet file directly rather than accepting a
   pre-loaded pandas DataFrame. Same dict shape, same keys.
3. `make_figure(df) -> matplotlib.figure.Figure` -- one chart that shows an
   informative view of this dataset (a per-category count bar chart and a
   valid-price distribution are both reasonable choices; pick whichever you
   think tells the more useful story, or make your own call).

## Completion criteria

From the module root (`14-stats-and-ml-foundations/`):

```bash
uv run python 02-eda-scraped-prices/tests/validate.py
```

The validator:

1. Calls `summarize_pandas(load_observations())` and `summarize_polars()`
   and checks the two dicts agree with each other -- numeric values within
   a float tolerance, dict/string values exactly. This is the pandas-vs-
   polars gate: if your two implementations disagree, at least one of them
   has a bug, and the validator will tell you which key.
2. Grades `n_obs`, `n_products`, and `per_category_count` against the
   module's committed `data/ground-truth.json` (these three are computed
   over ALL rows, no price filtering, so they match the ground truth
   exactly). The remaining facts depend on this task's specific "valid
   price" definition (see `src/eda.py`), which is intentionally simpler
   than a later task's defect-aware definition -- so those are graded
   against a reference the validator recomputes independently from
   `load_observations()` using the same definition you're asked to use.
3. Checks `make_figure(df)` returns a matplotlib Figure with actual drawn
   content (`require_figure`) -- it confirms a real chart exists, not that
   it's a *good* chart. Labeling, chart-type choice, and whether it
   actually communicates the finding are on you.

On success: `PASSED` with a handful of the key numbers. On an unfinished
scaffold: `NOT PASSED: <reason>`, exit 1, no traceback.

## Estimated evenings

1

## Topics to read up on

- pandas `groupby` / `value_counts` and aggregation (`.median()`,
  `.mean()`) on a filtered slice
- polars eager DataFrames and its expression API (`pl.col(...)`,
  `.filter(...)`, `.group_by(...).len()`) -- how it differs in shape from
  pandas even when eager, and how "lazy" (`.lazy()` / `.collect()`) changes
  the execution model for later, larger workloads
- median vs. mean on right-skewed data, and why a log-normal-shaped price
  column makes the two tell different stories
- data-quality first-pass habits: missingness rate, impossible values
  (non-positive prices), un-normalized categorical fields (currency)
- matplotlib basics: `Figure`/`Axes`, bar charts vs. histograms, linear vs.
  log-scaled axes for skewed distributions

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the dataset's exact generation process, and the full committed ground
truth -- spoilers. Don't read it before finishing this task.
