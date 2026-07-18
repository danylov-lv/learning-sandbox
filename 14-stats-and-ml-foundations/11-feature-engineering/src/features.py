"""t11 -- feature engineering: turn raw scraped columns into a feature
matrix that actually predicts price.

`src/baseline.py` (fully implemented, do not edit) gives you a WEAK feature
set -- `seller_rating`, `in_stock`, hour-of-day -- that scores close to
R^2 = 0 against `log(price)` on the held-out split. Your job is
`engineered_features` below: build a RICH feature set from the raw scraped
columns that beats that baseline by a wide margin, using ONLY columns that
are legitimately available before you know the price.

-------------------------------------------------------------------------
The leakage rule (read this before writing any code)
-------------------------------------------------------------------------
`engineered_features(df)` must derive every column it returns from
non-price fields only: `category`, `title`, `scraped_at`, `source_site`,
`in_stock`, `seller_rating`, `discount_pct`, `units_sold`, `currency`,
`product_id`, `obs_id`. NEVER read `df["price"]` (or anything computed
from it, like a per-category mean price) inside this function. Nothing in
`tests/validate.py` can mechanically prove you didn't -- there is no
target-leakage detector here, unlike the confound task -- so this is
enforced by you reading and following this paragraph, not by the
validator. A feature matrix that peeks at price would trivially "beat" the
baseline while teaching you nothing; the whole point of this task is
building predictive signal FROM RAW FIELDS, not memorizing the answer.

-------------------------------------------------------------------------
Where the real signal lives
-------------------------------------------------------------------------
Price is drawn from a per-category log-normal distribution (see
`generate.py` -- median and spread both depend on `category`). `category`
is therefore the single strongest predictor available, and it isn't
usable as-is: it's a string column, and a linear regressor needs numbers.
`title` also carries category signal (brand and noun vocabulary differ by
category, deliberately diluted so it's not a perfect proxy -- see
`.authoring/design.md` after you finish this task if you want the exact
dilution mechanics). `scraped_at` and `source_site` are weaker, but still
legitimately available raw fields worth trying.
"""

import numpy as np
import pandas as pd


def engineered_features(df):
    """Build a rich feature matrix from the raw scraped columns.

    Args:
        df: the full observations DataFrame, e.g.
            `harness.common.load_observations()` -- the SAME df you'd pass
            to `baseline.make_split` / `baseline.evaluate`. Do NOT
            pre-filter rows: the output must stay row-aligned with `df` (row
            i of the output describes row i of `df`) so `baseline.evaluate`
            can index it with `make_split(df)`'s train_idx/test_idx exactly
            like it does for `baseline_features`.

    Returns:
        A feature matrix with `len(df)` rows: a float64 ndarray, a pandas
        DataFrame (numeric dtypes only), or a scipy sparse matrix (e.g. if
        you use a `TfidfVectorizer`/`HashingVectorizer` over `title` and
        `scipy.sparse.hstack` it together with your dense columns). Any of
        these three shapes is accepted by `baseline.evaluate`.

    Build at least these four families of features (mixing weaker ones in
    on top only helps; none of them alone needs to carry the whole task):

    1. **Category, one-hot.** `df["category"]` takes one of 8 fixed string
       values. One-hot encode it -- one 0/1 column per category value (e.g.
       `pandas.get_dummies(df["category"])`) -- rather than an ordinal
       integer code: an ordinal code implies a numeric ordering between
       categories ("electronics < books") that doesn't exist and that a
       linear regressor will wrongly try to exploit.

    2. **`source_site`, one-hot.** Same idea, 3 values instead of 8.

    3. **Calendar features from `scraped_at`.** This column is a pandas
       datetime64 Series -- use its `.dt` accessor to pull out day-of-week,
       month, an `is_weekend` boolean, and hour. (`.dt.dayofweek`,
       `.dt.month`, `.dt.hour` are the relevant accessors; `is_weekend` is
       a simple comparison on `.dt.dayofweek`.) One-hot or leave numeric --
       your call.

    4. **Title-derived features.** `title` is a free-text string column.
       Two options, from simplest to richest:
         - Simple numeric features: title length (characters), word/token
           count, digit count, or a handful of hand-picked keyword
           indicators (e.g. "does the title contain any known brand/noun
           token for a given category").
         - A small text vectorizer: `sklearn.feature_extraction.text.
           TfidfVectorizer` or `HashingVectorizer`, fit (or hashed) on
           `df["title"]`, with a modest `max_features` so it stays a small
           addition rather than the whole feature matrix. This returns a
           sparse matrix -- combine it with your dense columns via
           `scipy.sparse.hstack` (and wrap your dense array with
           `scipy.sparse.csr_matrix(...)` first).

    Assemble every family into one matrix, row-aligned with `df`, and
    return it.
    """
    raise NotImplementedError
