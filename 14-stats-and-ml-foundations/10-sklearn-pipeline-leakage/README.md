# 10 -- sklearn Pipeline Leakage

## Backstory

A teammate built a quick regression model to predict price from the
scraped catalog -- category, seller rating, discount, a few other columns,
plus one clever addition: a per-product average price, learned from the
product's own history. Offline, the held-out R^2 looked great. Genuinely
good enough that "ship it" felt reasonable.

In production it didn't hold up. Predictions for products the model
handled well in evaluation were suddenly no better than a rough category
average -- which, on inspection, is basically all the model was ever
actually using. The "clever addition" was the problem: it was computed
across the whole dataset before anything got split into train and test,
which means every test row's own price had already been folded into its
own feature, just diluted enough not to look like cheating at a glance.
That's target leakage -- test-set information sneaking into the features
used to predict the test set -- and it is one of the most common ways an
offline metric lies to you about what a model will actually do once it
meets data it has truly never seen.

This task has you reproduce that exact bug on purpose, watch the score it
produces, then fix it and watch the score change. Same data, same model
architecture, same evaluation rows -- the only thing that moves is WHEN a
statistic gets computed relative to the train/test split.

## What's given

- `src/split.py` -- **fully implemented, not a stub.** `SPLIT_SEED = 42`,
  `TEST_SIZE = 0.2`, `valid_mask(df)` (which rows have a usable price), and
  `make_split(df)` -- a fixed, deterministic 80/20 split over the valid
  rows. Every function you write must call `make_split` rather than
  building its own split, so your grading and the validator's grading
  agree on which rows were held out. You do not need to modify this file.
- `src/leakage.py` -- the scaffold you implement. Three functions, each
  with a docstring that spells out the exact contract:
  - `build_pipeline()` -- an unfitted `sklearn.pipeline.Pipeline` for the
    non-leaky tabular features (category, source site, seller rating,
    discount, stock status, day of week).
  - `leaky_holdout_r2(df)` -- the WRONG way to add a target-encoded
    "average price for this product" feature.
  - `correct_holdout_r2(df)` -- the RIGHT way to add the same feature.
- The shared dataset, via `harness.common.load_observations()` -- the same
  scraped-catalog data every task in this module uses.

## What's required

Implement all three functions in `src/leakage.py`. `leaky_holdout_r2` and
`correct_holdout_r2` must use the same model architecture
(`build_pipeline()`) and the same held-out rows (`make_split`) -- the only
difference between them should be how the target-encoded feature gets
computed relative to the split. That isolation is what makes the
comparison mean something: whatever gap shows up between the two R^2
numbers is attributable to leakage, not to a different or better model.

## Completion criteria

From the module root:

```bash
uv run python 10-sklearn-pipeline-leakage/tests/validate.py
```

The validator calls all three functions and checks:

- `build_pipeline()` returns an actual `sklearn.pipeline.Pipeline`.
- `leaky_holdout_r2(df) - correct_holdout_r2(df)` is at least a chosen
  threshold -- the leak has to visibly, substantially inflate the score,
  not just nudge it.
- `correct_holdout_r2(df)` is at least a chosen (much lower) threshold --
  the honest model should still show real predictive signal (price in
  this dataset is strongly category-driven), not near-zero.

Prints `PASSED` with both R^2 numbers and the gap between them, or
`NOT PASSED: <reason>` and exits 1 -- including while `src/leakage.py` is
still unimplemented (`NotImplementedError` surfaces as a clean message, no
traceback).

## Estimated evenings

2

## Topics to read up on

- Data leakage / target leakage -- what it is and why it's one of the
  hardest classes of ML bug to catch from offline metrics alone
- Train/test contamination: any statistic derived from data (a mean, a
  scaler's fitted range, an encoding) must be fit on train data only and
  applied to test data, never the reverse
- `sklearn.pipeline.Pipeline` and `sklearn.compose.ColumnTransformer` --
  why wrapping preprocessing and modeling in one Pipeline object is the
  standard defense against leaking preprocessing statistics across a split
- Target encoding (mean encoding) of high-cardinality categorical
  features, and why it needs special care (out-of-fold encoding,
  regularization/smoothing, or a strict train-only fit) that a plain
  `OneHotEncoder` doesn't
- Cross-validation as a general defense against leakage -- and why it
  doesn't help if the leak happens before the CV split, only after
- R^2 as a regression metric: what it means, and why a number that looks
  "too good" for a genuinely noisy real-world target is itself a signal
  worth investigating rather than celebrating

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the exact dataset generation process, and this task's
verification margins -- spoilers. Don't read it before finishing this
task.
