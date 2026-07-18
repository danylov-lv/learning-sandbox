"""t07 -- the percentile bootstrap: a confidence interval for ANY statistic,
built by resampling your own data instead of leaning on an analytic formula.

Task 06 gave you a CI for the MEAN via the t-interval -- that formula exists
because the sampling distribution of a mean has a known, closed form (the
CLT). The MEDIAN has no such formula: its sampling distribution depends on
the shape of the underlying data in a way nobody has reduced to a plug-in
standard-error expression you can just look up. Same story for percentiles,
ratios, or any statistic that isn't a simple sum. The bootstrap sidesteps
this entirely: treat your OWN sample as a stand-in for the population, draw
many new samples FROM it (with replacement, same size), recompute the
statistic on each resample, and read the spread of those recomputed values
as your uncertainty. No formula, no distributional assumption about the
statistic itself -- just resampling and arithmetic.

This module applies it to the median of scraped USD prices.

--------------------------------------------------------------------------
THE PINNED RECIPE -- read this before writing any code. The validator
reproduces these exact steps independently; if your implementation follows
this recipe precisely, your numbers will match its numbers to within a
tight tolerance. Deviate from the recipe (different rng calls, different
call order, sampling without replacement, re-seeding inside the loop) and
your CI will drift, sometimes a lot.
--------------------------------------------------------------------------

Base sample (already done for you -- see `load_valid_usd_prices` and
`draw_base_sample` below, not a stub):

1. Pull every observation from `load_observations()` whose `currency` is
   `"USD"`, whose `price` is not NaN, and whose `price` is > 0. This is the
   "valid USD price" population for this task.
2. Draw `SAMPLE_SIZE` of them ONCE, without replacement, via
   `np.random.default_rng(SAMPLE_SEED).choice(n_valid, size=SAMPLE_SIZE,
   replace=False)`. This fixed draw is "your sample" -- the one dataset a
   real analyst would actually have in hand. Everything below resamples
   FROM this array; it never goes back to the full population.

Bootstrap resampling (this is what you implement):

1. Create exactly one `rng = np.random.default_rng(BOOTSTRAP_SEED)` before
   the loop starts -- not one per iteration.
2. For `r in range(n_resamples)`: draw `idx = rng.integers(0, n, size=n)`
   where `n = len(sample)` (WITH replacement -- indices can repeat, and
   some original points may not appear at all in a given resample). Compute
   `statistic_fn(sample[idx])` and store it as the r-th entry of the output
   array.
3. The percentile CI is just `np.percentile` (default linear
   interpolation) of that array of `n_resamples` statistics, at the
   `100 * alpha / 2` and `100 * (1 - alpha / 2)` percentiles, where
   `alpha = 1 - confidence`.

That's the whole method. The rest is bookkeeping.
"""

import numpy as np

SAMPLE_SEED = 20260718
SAMPLE_SIZE = 300
BOOTSTRAP_SEED = 12345
N_RESAMPLES = 2000
CONFIDENCE = 0.95
STATISTIC = np.median


# --------------------------------------------------------------------------
# Provided infrastructure -- NOT a stub, don't need to touch this. Loads the
# shared dataset and draws the one fixed base sample the rest of the task
# resamples from. Reads harness.common.load_observations(), which is module
# 14's shared dataset loader (see harness/common.py at the module root).
# --------------------------------------------------------------------------

def load_valid_usd_prices() -> np.ndarray:
    """Return every valid USD price in the shared dataset as a 1-D array.

    "Valid" here means: `currency == "USD"`, `price` is not NaN, and
    `price > 0`. This intentionally does NOT try to reconstruct the
    generator's full defect-detection logic (task 05's job) -- it's a
    simple, mechanical filter anyone reading `load_observations()`'s output
    could apply, which is exactly what makes it reproducible without access
    to any hidden ground truth.
    """
    import sys
    from pathlib import Path

    module_root = Path(__file__).resolve().parents[2]
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
    from harness.common import load_observations

    df = load_observations()
    valid = df[(df["currency"] == "USD") & df["price"].notna() & (df["price"] > 0)]
    return valid["price"].to_numpy()


def draw_base_sample() -> np.ndarray:
    """Draw the one fixed base sample this task's bootstrap resamples from:
    `SAMPLE_SIZE` valid USD prices, drawn once without replacement via
    `np.random.default_rng(SAMPLE_SEED)`. Calling this twice returns the
    same array both times (deterministic, seeded)."""
    prices = load_valid_usd_prices()
    rng = np.random.default_rng(SAMPLE_SEED)
    idx = rng.choice(len(prices), size=SAMPLE_SIZE, replace=False)
    return prices[idx]


# --------------------------------------------------------------------------
# Your implementation starts here.
# --------------------------------------------------------------------------

def bootstrap_distribution(
    sample: np.ndarray,
    statistic_fn,
    n_resamples: int = N_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> np.ndarray:
    """Build the bootstrap sampling distribution of `statistic_fn` over
    `sample`, following the PINNED RECIPE in this module's docstring.

    Args:
        sample: 1-D array of observed values (e.g. `draw_base_sample()`'s
            output, or any other array -- this function must work for any
            `sample`, not just the pinned one).
        statistic_fn: a callable, `statistic_fn(array) -> float`, e.g.
            `np.median`. Applied to each resample.
        n_resamples: how many bootstrap resamples to draw.
        seed: seed for a SINGLE `np.random.default_rng(seed)` created once,
            before the loop -- re-seeding inside the loop (or creating a
            fresh rng per iteration) breaks reproducibility with the
            validator's reference and is not the recipe this task pins.

    Returns:
        A 1-D array of length `n_resamples`: `statistic_fn` evaluated on
        each of the `n_resamples` resamples, in the order they were drawn.

    Recipe (repeated from the module docstring -- follow it exactly):
        rng = np.random.default_rng(seed)          # once
        n = len(sample)
        for r in range(n_resamples):
            idx = rng.integers(0, n, size=n)        # WITH replacement
            out[r] = statistic_fn(sample[idx])
    """
    raise NotImplementedError


def percentile_ci(boot_stats: np.ndarray, confidence: float = CONFIDENCE) -> tuple[float, float]:
    """Compute the percentile confidence interval from an already-built
    bootstrap distribution.

    Args:
        boot_stats: 1-D array of bootstrap statistics (e.g.
            `bootstrap_distribution(...)`'s output).
        confidence: e.g. `0.95` for a 95% CI.

    Returns:
        `(low, high)`: the `100 * alpha / 2` and `100 * (1 - alpha / 2)`
        percentiles of `boot_stats`, where `alpha = 1 - confidence`, via
        `np.percentile` (default linear interpolation -- don't pass a
        different `method=`/`interpolation=`, the validator uses the
        default too).
    """
    raise NotImplementedError


def bootstrap_ci(
    sample: np.ndarray,
    statistic_fn,
    n_resamples: int = N_RESAMPLES,
    confidence: float = CONFIDENCE,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Convenience wrapper: build the bootstrap distribution and reduce it
    to a percentile CI in one call.

    Must be equivalent to
    `percentile_ci(bootstrap_distribution(sample, statistic_fn, n_resamples,
    seed), confidence)` -- this function should not reimplement the
    resampling loop or the percentile math differently from the two
    functions above; it exists so callers don't have to wire the two steps
    together by hand every time.

    Args:
        sample: 1-D array of observed values.
        statistic_fn: callable, `statistic_fn(array) -> float`.
        n_resamples: how many bootstrap resamples to draw.
        confidence: e.g. `0.95` for a 95% CI.
        seed: seed for the single rng driving the resampling.

    Returns:
        `(low, high)` percentile CI bounds.
    """
    raise NotImplementedError


def make_figure(boot_stats: np.ndarray, ci: tuple[float, float]):
    """Build a matplotlib Figure visualizing the bootstrap distribution.

    Args:
        boot_stats: 1-D array of bootstrap statistics (what
            `bootstrap_distribution` returns).
        ci: `(low, high)` percentile CI bounds (what `percentile_ci`
            returns).

    Returns:
        A `matplotlib.figure.Figure` with at least one Axes containing:
        - a histogram of `boot_stats` (this is the bootstrap sampling
          distribution -- the whole point of the plot is to make its shape
          and spread visible),
        - two vertical lines marking `ci[0]` and `ci[1]` (the CI bounds),
        - a third vertical line or marker for the point estimate. `boot_stats`
          and `ci` are all this function receives, so use `np.median(boot_stats)`
          as the point estimate -- the bootstrap distribution is centered
          near the statistic computed on the original sample, close enough
          for this plot's purpose. Make it visually distinct from the two
          CI-bound lines (different color, style, or label) so a reader
          can't confuse "the estimate" with "a CI edge."

        Label the axes and add a legend or annotations identifying which
        line is which -- `tests/validate.py` only checks that a figure
        exists and has drawn content (via `require_figure`); it cannot
        judge whether the labeling makes the plot readable. That part is on
        you.
    """
    raise NotImplementedError
