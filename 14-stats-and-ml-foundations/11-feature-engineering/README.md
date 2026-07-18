# 11 -- Feature Engineering

## Backstory

You wire up a quick price model as a sanity check before anything fancier:
throw the "obviously relevant-looking" numeric columns at a regressor --
seller rating, discount percentage, whether it's in stock -- and see what
comes out. What comes out is garbage. R^2 close to zero. The model can't
explain the price of anything.

The columns you grabbed aren't wrong, exactly -- they're just not where the
signal lives. You skipped the two richest columns in the table because
they're not numbers: `category` is a string, and `title` is free text.
Nobody hands you a regressor-ready matrix; you build one. This task is
about turning the raw scraped columns you have -- categorical fields,
timestamps, product titles -- into numeric features that actually carry
the information a regressor can use, and proving, with a number, how much
that transformation is worth.

## What's given

- `src/baseline.py` -- **fully implemented, not a stub.** Four pieces, all
  fixed so your results and the validator's agree:
  - `SPLIT_SEED = 42`, `TEST_SIZE = 0.2`.
  - `make_split(df)` -- builds the train/test row split, always the same
    for a given `df`. Both your experimentation and the validator call
    this on the full dataset.
  - `baseline_features(df)` -- the weak feature set: `seller_rating`,
    `in_stock`, and hour-of-day. Read the module docstring in that file --
    it explains, with a measured number, why the obvious-looking
    `discount_pct` column was deliberately left OUT of the weak baseline
    (it's confounded with category, so it isn't actually weak -- a useful
    lesson in itself).
  - `evaluate(features, df)` -- fits a fixed `Ridge(alpha=1.0)` regressor
    on the train split, scores R^2 on the test split. Both the baseline and
    your engineered features are scored through this same function.
- The shared dataset at `../data/observations.parquet`, loaded via
  `harness.common.load_observations()`.

## What's required

Implement `engineered_features(df)` in `src/features.py`: a feature matrix,
row-aligned with `df`, built from the raw scraped columns (never from
`price` itself -- see the leakage rule in that file's docstring). At
minimum, cover:

1. **`category`, one-hot encoded.** This is where most of the signal is --
   price is drawn from a per-category distribution, so category alone
   predicts a lot.
2. **`source_site`, one-hot encoded.**
3. **Calendar features pulled out of `scraped_at`** -- day-of-week, month,
   is-weekend, hour.
4. **Something derived from `title`** -- at minimum simple numeric features
   (length, word count, digit count); a small `TfidfVectorizer` /
   `HashingVectorizer` over the title text goes further.

`src/features.py`'s docstring spells out the exact contract (row alignment,
accepted return shapes: ndarray, DataFrame, or scipy sparse matrix) and the
leakage rule in full -- read it before writing code.

## Completion criteria

From the module root:

```bash
uv run python 11-feature-engineering/tests/validate.py
```

The validator:

- Computes `base_r2 = evaluate(baseline_features(df), df)` and
  `eng_r2 = evaluate(engineered_features(df), df)` on the SAME fixed split.
- Sanity-gates `base_r2` itself (it should stay close to 0 -- if it
  doesn't, the fixture or dataset changed, not your code).
- Requires `eng_r2 - base_r2` to clear a wide, explicit margin.
- Requires `eng_r2` to reach a solid absolute value on its own.

Prints `PASSED: base_r2=..., eng_r2=..., gain=...` or `NOT PASSED: <reason>`
and exits 1 -- including when `features.py` is still unimplemented
(`NotImplementedError` surfaces as a clean message, no traceback).

## Estimated evenings

1-2

## Topics to read up on

- One-hot encoding vs. ordinal/label encoding for categorical features --
  why a linear model treats an ordinal code as an implied numeric ordering
  that usually doesn't exist
- Datetime feature extraction: pulling day-of-week, month, hour, and
  weekend/weekday out of a timestamp column
- Text features: bag-of-words, TF-IDF, and hashing vectorizers as ways to
  turn free text into numeric columns
- Feature-target relationship: why "a column that looks plausible" and "a
  column that actually predicts the target" are different claims, checked
  by measuring, not by intuition
- R^2 as a regression metric: what 0, negative, and close-to-1 values mean
- Not leaking the target: why a feature computed from the value you're
  predicting (directly or through an aggregate) makes a model look good
  for the wrong reason

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the dataset's exact generation process (including the category price
profile and the title dilution mechanics), and this task's exact
verification margins -- spoilers. Don't read it before finishing this task.
