"""t01 -- vectorization and broadcasting: your implementation.

Reimplement each function in `src/naive.py` with the SAME signature and the
SAME output, but without a Python-level loop over the n rows. Every one of
these must produce results matching `naive.py`'s functions within floating-
point tolerance (`np.allclose`) -- this is not a "different algorithm that
happens to look similar" exercise, it's the exact same computation done as
whole-array numpy operations instead of a per-row Python loop.

A small loop over the handful of DISTINCT group codes (there are only a few
categories in this dataset) is acceptable -- you are not looping over rows.
A loop that iterates once per element of `prices`/`values` (however it's
spelled -- `for`, a list comprehension over indices, `.apply()` with a
Python callable, etc.) is not; it defeats the point of the task.

See `src/naive.py`'s docstrings for the exact semantics you must match
(what "within each category" means, how the rolling window handles the
start of the array, how a constant group is scaled). `ROLLING_WINDOW` is
also defined there -- import it rather than redefining it.
"""

import numpy as np


def zscore_within_category(prices: np.ndarray, category_codes: np.ndarray) -> np.ndarray:
    """Vectorized equivalent of naive.zscore_within_category.

    Args:
        prices: 1-D float64 array, length n, finite values only.
        category_codes: 1-D integer array, length n. For this task, codes
            are small non-negative ints in [0, K) for some small K (one
            code per category) -- suitable for `np.bincount`-style
            grouped aggregation keyed directly by code value.

    Returns:
        float64 array, length n: out[i] = (prices[i] - mean(group)) /
        std(group, ddof=0), where group = every j with
        category_codes[j] == category_codes[i]. Must match
        naive.zscore_within_category's output within floating-point
        tolerance (np.allclose).

    Intended approach: compute per-group sums and counts in one pass each
    with `np.bincount` (using `weights=` for the sum), derive per-group
    means and stds from those, then broadcast each row's group mean/std
    back to row shape by indexing the per-group array with
    `category_codes` itself (fancy indexing: `means[category_codes]` is a
    length-n array). No loop over rows.
    """
    raise NotImplementedError


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Vectorized equivalent of naive.rolling_mean.

    Args:
        values: 1-D float64 array, length n, finite values only.
        window: trailing window size, a positive int. Same semantics as
            naive.rolling_mean: window shrinks (never looks before index
            0) for i < window - 1, fixed size window at and after that.

    Returns:
        float64 array, length n. Must match naive.rolling_mean's output
        within floating-point tolerance (np.allclose).

    Intended approach: a running total via `np.cumsum` lets you get the
    sum of any contiguous slice as a difference of two cumulative-sum
    entries in O(1) per row, without re-summing the window's elements
    every time (which is what makes naive.rolling_mean O(n * window)
    instead of O(n)). Watch the edges: the window's start index needs to
    clip at 0, and the divisor is the ACTUAL window length at each
    position (shorter than `window` for the first `window - 1` rows), not
    a constant `window`.
    """
    raise NotImplementedError


def minmax_scale_per_group(values: np.ndarray, group_codes: np.ndarray) -> np.ndarray:
    """Vectorized equivalent of naive.minmax_scale_per_group.

    Args:
        values: 1-D float64 array, length n, finite values only.
        group_codes: 1-D integer array, length n. Same code convention as
            zscore_within_category's category_codes (small non-negative
            ints in [0, K)).

    Returns:
        float64 array, length n, every value in [0, 1] (or exactly 0.0 for
        a constant group -- same special case as naive.py). Must match
        naive.minmax_scale_per_group's output within floating-point
        tolerance (np.allclose).

    Intended approach: numpy has no single whole-array "grouped min/max"
    primitive as cheap as bincount's grouped sum, so a small loop over the
    handful of DISTINCT group codes (not over rows) -- boolean-masking out
    each group's rows and taking a plain `.min()` / `.max()` over just
    that slice -- is the intended shape here. That loop runs a number of
    times equal to the number of distinct groups, not n.
    """
    raise NotImplementedError
