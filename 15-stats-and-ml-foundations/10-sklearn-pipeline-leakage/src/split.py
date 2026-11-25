"""Shared split fixture for t10 (sklearn-pipeline-leakage).

This file is GIVEN, fully implemented -- not a stub. Every function in
`src/leakage.py` and the validator must grade on the exact SAME held-out
rows, so the train/test split is fixed here once, with a fixed seed, and
imported everywhere else. Do not re-split with a different seed or a
different function anywhere in this task -- that would silently disagree
with what the validator expects, and would also break the point of the
exercise: leaky vs. correct only means something if both are evaluated on
the same held-out rows.

`make_split` only ever looks at whether a row is usable at all (a valid
price in USD) -- it says nothing about product_id, target encoding, or
leakage. That is entirely the concern of `src/leakage.py`.
"""

import numpy as np
from sklearn.model_selection import train_test_split

# Fixed split contract -- shared by src/leakage.py and tests/validate.py.
# Do not change these values; changing them changes which rows are held out
# and silently invalidates the R^2 thresholds tuned against this split.
SPLIT_SEED = 42
TEST_SIZE = 0.2


def valid_mask(df):
    """Boolean mask (pandas Series, same index as df): True for rows this
    task treats as usable at all.

    A row is valid iff:
      - `price` is not NaN
      - `price` > 0
      - `currency` == "USD"

    This does NOT filter on anything else (category, in_stock, etc.) --
    those are features, not validity criteria. Roughly 4.5% of rows fail
    this (planted price-parsing defects: negative, zero, missing-decimal,
    NaN) and another ~2% are non-USD and excluded rather than converted.
    """
    return df["price"].notna() & (df["price"] > 0) & (df["currency"] == "USD")


def make_split(df):
    """Deterministic 80/20 train/test split over the VALID rows of df.

    Args:
        df: the full observations DataFrame, exactly as returned by
            `harness.common.load_observations()` -- a default RangeIndex
            (0 .. len(df)-1), unfiltered (includes the ~4.5% price-defect
            rows and the ~2% non-USD rows).

    Returns:
        (train_idx, test_idx): two 1-D numpy int arrays of POSITIONAL row
        indices into `df` (i.e. usable with `df.iloc[...]`), disjoint,
        covering exactly the VALID rows (per `valid_mask`) between them --
        every invalid row is in neither array. `len(test_idx) /
        (len(train_idx) + len(test_idx)) ~= TEST_SIZE`.

        Built via `sklearn.model_selection.train_test_split` on the valid
        positional indices, with `test_size=TEST_SIZE,
        random_state=SPLIT_SEED` -- the ONE fixed split every function in
        this task must use, so the learner's train/test split and the
        validator's grading split are the exact same rows.

    Every function you write in `src/leakage.py` that needs a train/test
    split must call this function rather than constructing its own split.
    """
    valid_idx = np.flatnonzero(valid_mask(df).to_numpy())
    train_idx, test_idx = train_test_split(
        valid_idx, test_size=TEST_SIZE, random_state=SPLIT_SEED,
    )
    return train_idx, test_idx
