"""t10 -- sklearn pipeline leakage: the target-encoding trap.

The task: predict `y = log(price)` for the shared scraped-catalog dataset,
using a proper sklearn `Pipeline`, and then watch a single feature-
engineering choice swing the held-out R^2 by a wide, reproducible margin --
not because the model changed, but because of WHEN a statistic gets
computed relative to the train/test split.

The feature in question is a target-encoded `product_mean_logprice`: the
average `log(price)` for a product, keyed by its high-cardinality
`product_id` (~8000 distinct products, ~5-8 observations each in the valid
data). Averaging a product's own price history into a feature for that
product is a completely ordinary thing to want to do. The trap is HOW you
average:

  - Average over the WHOLE dataset (including test rows) before splitting,
    and a test row's own `log(price)` is baked into its own feature value
    -- for a product with only 1-2 observations, that's most or all of the
    "average." The model isn't predicting the price; it's decoding a
    smoothed copy of the answer you handed it. `leaky_holdout_r2` measures
    what this looks like.
  - Average using ONLY the train rows, and a held-out test row's feature
    value was computed without ever seeing that row's own target. Products
    that only appear in the test split (never seen in train) fall back to
    the train-wide average log-price, exactly the way an unseen category
    level would in any encoding scheme. `correct_holdout_r2` measures what
    this looks like.

Both functions share the exact same model architecture (`build_pipeline`)
and the exact same held-out rows (`src.split.make_split`, imported below).
The only thing that differs between them is which rows contributed to the
`product_mean_logprice` value attached to each row before fitting. That
isolation is the whole point: whatever gap shows up between the two R^2
numbers is caused by leakage, not by a better or worse model.

Shared feature-column constants, used by all three functions below so the
column set `build_pipeline`'s `ColumnTransformer` expects always matches
the column set `leaky_holdout_r2` / `correct_holdout_r2` actually build:

  CATEGORICAL_FEATURES = ["category", "source_site"]
  NUMERIC_FEATURES     = ["seller_rating", "discount_pct", "in_stock", "day_of_week"]

`day_of_week` is not a column in the raw dataset -- derive it from
`scraped_at` (`.dt.dayofweek`, Monday=0..Sunday=6) before it can be used.
`in_stock` is a bool column; cast it to a numeric dtype (e.g. `.astype(float)`)
before handing it to a `StandardScaler`, which expects numeric input.

Every function below is expected to internally restrict to VALID rows
(`src.split.valid_mask`) before computing `y = np.log(price)` -- `price`
is only positive and finite on valid rows; taking `log` of an invalid
row's `price` (0, negative, or NaN) produces `-inf`/`NaN` and will corrupt
any groupby mean it touches, INCLUDING other products' valid rows if you
average before filtering. Filter first, then take logs, then group.
"""

from src.split import make_split, valid_mask  # noqa: F401

CATEGORICAL_FEATURES = ["category", "source_site"]
NUMERIC_FEATURES = ["seller_rating", "discount_pct", "in_stock", "day_of_week"]


def build_pipeline():
    """Build (but do not fit) a scikit-learn Pipeline for the non-leaky
    tabular features.

    Returns:
        sklearn.pipeline.Pipeline, UNFITTED (do not call `.fit()` inside
        this function -- `leaky_holdout_r2` / `correct_holdout_r2` call it
        once each, fresh, and fit each copy on their own train split).

    Required shape:

      1. A `sklearn.compose.ColumnTransformer` as the first step, with:
         - `OneHotEncoder(handle_unknown="ignore")` applied to
           `CATEGORICAL_FEATURES` (`handle_unknown="ignore"` matters: a
           category value the encoder never saw in train -- shouldn't
           happen here since all 8 categories and all 3 source sites are
           common, but is good practice and costs nothing -- would
           otherwise raise at transform time instead of degrading
           gracefully).
         - `StandardScaler()` applied to `NUMERIC_FEATURES`.
         - `remainder="passthrough"`. This is required, not optional: it
           is what lets `leaky_holdout_r2` and `correct_holdout_r2` attach
           an EXTRA numeric column (`product_mean_logprice`) to the input
           DataFrame and have this same pipeline pick it up automatically
           as one more numeric input to the regressor, without having to
           duplicate or edit the `ColumnTransformer`'s column list. Without
           `remainder="passthrough"` (the default is `remainder="drop"`),
           any column not explicitly named above would be silently
           dropped, and the leaky/correct comparison would only ever be
           testing the SAME leak-free feature set twice.

      2. A regressor as the final step, fit on whatever the
         `ColumnTransformer` outputs. `sklearn.linear_model.Ridge()` and
         `sklearn.ensemble.HistGradientBoostingRegressor()` both work well
         here and need no special hyperparameters; pick either (or
         something else reasonable) as long as it exposes the usual
         `.fit(X, y)` / `.predict(X)` interface expected by a Pipeline's
         last step.

    The input DataFrame `X` this pipeline is later `.fit()` / `.predict()`ed
    on must contain, at minimum, every name in `CATEGORICAL_FEATURES` and
    `NUMERIC_FEATURES` as columns (plus, when called from
    `leaky_holdout_r2` / `correct_holdout_r2`, the extra
    `product_mean_logprice` column that `remainder="passthrough"` lets
    through) -- building that DataFrame is the caller's job, not this
    function's.
    """
    raise NotImplementedError


def leaky_holdout_r2(df):
    """The WRONG way to add a target-encoded feature: compute it before
    splitting, so it leaks each test row's own target into its own
    features.

    Args:
        df: the full observations DataFrame, exactly as returned by
            `harness.common.load_observations()`.

    Returns:
        float: R^2 (e.g. `sklearn.metrics.r2_score`, or
        `Pipeline.score(X_test, y_test)`, which computes the same thing)
        of the fitted pipeline's predictions on the held-out test rows.

    Steps:

      1. Restrict to valid rows (`valid_mask`) and compute
         `y = np.log(price)` for them.
      2. Compute `product_mean_logprice` as the mean of `y` PER
         `product_id`, grouping over ALL valid rows -- train and test
         rows together, before any split has happened. Attach this as a
         column, keyed by `product_id`, to every valid row (a row whose
         product appears twice in the valid data gets the same
         `product_mean_logprice` both times; a row is always included in
         its OWN product's average).
      3. Only now call `make_split(df)` to get `train_idx` / `test_idx`.
      4. Build the feature matrix (`CATEGORICAL_FEATURES` +
         `NUMERIC_FEATURES` + `product_mean_logprice`) and target `y` for
         the train rows and the test rows separately.
      5. `build_pipeline()`, `.fit()` on the train rows, score on the test
         rows.

    Why this leaks: for a product with only 1-2 observations in the valid
    data (common -- the dataset averages ~5-8 valid observations per
    product, and that's an average, not a floor), a test row's own
    `log(price)` makes up most or all of that product's
    `product_mean_logprice`. The "feature" is, for those rows, very close
    to a smoothed copy of the answer.
    """
    raise NotImplementedError


def correct_holdout_r2(df):
    """The RIGHT way to add the same target-encoded feature: split first,
    compute the encoding from train rows only, and let unseen products
    fall back to the train-wide mean.

    Args:
        df: the full observations DataFrame, exactly as returned by
            `harness.common.load_observations()`.

    Returns:
        float: R^2 of the fitted pipeline's predictions on the held-out
        test rows, computed the same way as `leaky_holdout_r2` (so the two
        numbers are directly comparable).

    Steps:

      1. Call `make_split(df)` FIRST to get `train_idx` / `test_idx`.
      2. Restrict to valid rows and compute `y = np.log(price)` (same as
         `leaky_holdout_r2`).
      3. Compute `product_mean_logprice` as the mean of `y` PER
         `product_id`, grouping over TRAIN rows ONLY.
      4. For a `product_id` that never appears in the train rows (it only
         shows up in the test split), there is no train-derived mean for
         it -- fall back to the GLOBAL mean of `y` over all train rows
         (the same fallback an unseen category level gets in any target-
         encoding scheme). Attach `product_mean_logprice` to every row
         (train and test) this way.
      5. Build the same feature matrix as `leaky_holdout_r2`
         (`CATEGORICAL_FEATURES` + `NUMERIC_FEATURES` +
         `product_mean_logprice`) for train and test rows, using
         `build_pipeline()` for the base tabular-feature architecture so
         the two functions are comparing the same model, not a different
         one.
      6. `.fit()` on the train rows, score on the test rows.

    A handful of test-split products (this dataset: a few dozen out of
    ~5000+ distinct products touched by the test split) will hit the
    fallback in step 4 -- that's expected, not a bug: those products
    genuinely have zero train-time information available about them.
    """
    raise NotImplementedError
