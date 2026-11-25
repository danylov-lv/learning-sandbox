# 05 -- Outliers vs. Parsing Errors

## Backstory

The finance team's weekly "average product price" mart jumped 40% overnight.
Nobody shipped a pricing change. What actually happened: a batch of scraped
prices came through with a dropped decimal point -- a few hundred products
whose real price was something like $19.99 got recorded as $1999 -- and
those x100 values dragged every downstream average with them.

Someone on the data team shipped a same-day fix: "just drop anything above
the 99th percentile, problem solved." It stopped the mart from exploding.
It also silently deleted a chunk of your genuinely premium products --
the real $1,800 flagship electronics, the real $500 sporting-goods
equipment -- because a blanket percentile cutoff (or "flag anything > 3
standard deviations from the mean," the same idea in different clothes)
cannot tell "this value is fake" from "this value is real and just large."
Both look like outliers to that rule. Only one of them should be thrown
away.

This task is the fix, done properly: separate the two failure modes
instead of erasing them together.

## What's given

The `price` column in the shared dataset (`data/observations.parquet`,
loaded via `harness.common.load_observations()`) contains, mixed together:

- **Parsing errors** (~4.5% of rows total, split roughly evenly across four
  kinds -- these are all planted defects, told to you up front so the
  challenge here is method, not guessing):
  - `negative` -- price recorded as a negative number.
  - `zero` -- price recorded as exactly `0`.
  - `missing_decimal` -- the decimal point got dropped somewhere upstream,
    so the recorded price is ~100x a plausible price for that row's
    category (e.g. a real $19.99 item shows up as $1999).
  - `nan` -- price is missing (an unparseable "N/A" or similar).
- **Genuine outliers** -- real, unusually expensive products. Defined (for
  your own intuition, not something your code needs to reproduce exactly)
  as products whose price genuinely sits in the top slice of their
  category's distribution. Large, but not an artifact of anything breaking.
  These must survive your classification untouched.

Currency is a separate, independent data-quality axis: ~2% of rows carry a
non-USD currency code. That's out of scope for this task -- don't treat a
non-USD row as a price defect just because of its currency; classify it
based on `price` alone, same as every other row. ("Parsing error," here,
means a `price`-column defect only.)

You do NOT get told which specific rows are defective, which kind each one
is, or which rows are the genuine outliers -- that partition is exactly
what you're building.

- `src/quality.py` -- the scaffold you implement. Two functions,
  `classify_prices(df)` and `make_figure(df)`, each with a rich docstring
  spelling out the contract and the shape of a working approach. No
  solution code.
- `tests/validate.py` -- reconstructs the hidden ground truth (which rows
  are defective, which kind, which are genuine outliers) independently of
  your code and grades your classification against it.

## What's required

Implement `classify_prices(df) -> dict` in `src/quality.py`, returning:

- `parsing_error_ids`: the `obs_id` values you're quarantining as price
  parsing errors.
- `kept_ids`: every other `obs_id` -- including genuine outliers. Together
  the two sets must partition every row in `df` exactly once.

Implement `make_figure(df) -> matplotlib.figure.Figure`: a plot that makes
the separation visible -- parsing errors and kept values (genuine outliers
included) distinguished from each other, on a scale that doesn't collapse
the whole distribution into one bar (this column spans several orders of
magnitude once you include the defects).

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate.py
```

`tests/validate.py` grades your `parsing_error_ids` against the dataset's
hidden ground truth (the exact defect/outlier partition the generator
planted, reconstructed independently of your code):

- `negative`, `zero`, and `nan` rows must be caught with 100% recall --
  these are unambiguous, there's no excuse for missing one.
- `missing_decimal` rows must be caught with high recall (most of them --
  a handful of borderline cases are tolerated).
- **The gate that actually matters:** zero genuine outliers may end up in
  your `parsing_error_ids`. Flagging a real, expensive product as a parsing
  error is exactly the mistake this task exists to catch, and it fails the
  task outright, no partial credit. Your flagged set's overall precision
  against true defects must also stay high -- quarantining ordinary
  mid-range prices "just in case" fails too.
- `make_figure(df)` must return a Figure with real drawn content.

Prints `PASSED` with the measured per-kind recall and the genuine-outlier
false-positive count, or `NOT PASSED: <reason>` and exits 1 -- including
when `quality.py` is still unimplemented.

## Estimated evenings

2

## Topics to read up on

- Robust statistics: median and MAD (median absolute deviation) vs. mean
  and standard deviation, and why the latter pair breaks down in the
  presence of a handful of extreme values
- The IQR rule for outlier detection, and its limits
- Why a z-score / "N standard deviations" test fails on skewed
  (log-normal-shaped) data, and why looking at the data on a log scale
  often fixes it
- Distinguishing a data-entry/parsing error from a true statistical outlier
  -- these are different questions and need different tests
- Order-of-magnitude / decimal-shift error signatures in real-world scraped
  or manually-entered numeric data

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the dataset's exact defect-planting and outlier construction, and this
task's verification margins -- spoilers. Don't read it before finishing
this task.
