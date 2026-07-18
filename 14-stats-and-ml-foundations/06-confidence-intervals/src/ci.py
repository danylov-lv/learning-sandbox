"""06 -- Confidence intervals for a scraped price mean.

You scraped a category's worth of product pages and computed the average
price. This module is about the honest next question: how much do you
trust that average? A sample mean is itself a random variable -- draw a
different 200 pages and you'd get a slightly different number. A
confidence interval quantifies that uncertainty; the 1/sqrt(n) law tells
you how many more pages it would take to cut it in half.

Fixed sampling recipe (so your numbers and the validator's numbers agree
on the exact same sample)
--------------------------------------------------------------------------
Population: every VALID price (no parsing defects, USD currency only) for
CATEGORY = "electronics", reconstructed by `load_population()` below
(given -- do not modify). "Valid" here means the same thing it means
everywhere else in this module: not one of the four planted price defects
(negative / zero / missing_decimal / nan) and not a non-USD row. Filtering
that out is not this task's subject -- `load_population()` does it for
you, deterministically, from the same dataset build the validator uses.

The primary fixed sample:

    rng = np.random.default_rng(SAMPLE_SEED)
    idx = rng.choice(len(population), size=SAMPLE_SIZE, replace=False)
    sample = population[idx]

`SAMPLE_SEED = 20240718`, `SAMPLE_SIZE = 200`. Every function below that
takes a `seed` argument uses this exact recipe: build (or receive) the
population array, then `np.random.default_rng(seed).choice(len(population),
size=n, replace=False)` -- same order of operations every time, so the
draw is reproducible bit-for-bit.
"""

import sys
from pathlib import Path

import numpy as np

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

CATEGORY = "electronics"
SAMPLE_SEED = 20240718
SAMPLE_SIZE = 200

# Sizes used to demonstrate the 1/sqrt(n) shrink of CI width. Because the
# electronics price population is right-skewed (log-normal draw, plus a
# genuine long tail), a SINGLE sample at each size is noisy -- one unlucky
# high-price draw can swing a small sample's width a lot. WIDTH_REPEATS
# independent draws per size, averaged, is what makes the 1/sqrt(n) trend
# show up cleanly instead of being buried in sampling noise. This is
# Monte Carlo, not cheating: the *expected* CI width really does scale as
# 1/sqrt(n); a single realization is just a noisy estimate of it.
WIDTH_SIZES = [50, 100, 200, 400, 800]
WIDTH_REPEATS = 100


def load_population(category: str = CATEGORY) -> np.ndarray:
    """GIVEN -- fully implemented, do not modify.

    Rebuilds the full observation set the same way `generate.py` did (same
    seed, same row count) and returns every valid USD price for `category`
    as a 1-D float array, in the row order `build_observations` produces
    them. "Valid" excludes the four planted price defects (negative, zero,
    missing_decimal, nan) and non-USD currency rows -- see task 05 if you
    want to understand how those are detected; here they're just filtered
    out so the population this task samples from is clean.

    This is the SAME reconstruction the validator does, so calling this
    with the default `category` always returns the identical array (same
    values, same order) on your machine and the validator's.
    """
    import generate
    from harness.common import load_ground_truth

    gt = load_ground_truth()
    df, labels = generate.build_observations(generate.SEED, gt["n_obs"])
    valid = labels["valid_mask"] & (df["category"] == category).to_numpy()
    return df["price"].to_numpy()[valid]


def mean_confidence_interval(
    sample: np.ndarray, confidence: float = 0.95
) -> tuple[float, float]:
    """Student t confidence interval for the mean of `sample`.

    The sample mean has its own sampling distribution with standard error
    SE = s / sqrt(n), where s is the sample's standard deviation (ddof=1,
    i.e. divide by n-1 -- `scipy.stats.sem` does this by default). Because
    the population standard deviation is unknown and estimated from the
    same sample, the correct critical value comes from the Student t
    distribution with n-1 degrees of freedom, not the normal (z)
    distribution -- the difference matters most at small n and shrinks
    toward the normal critical value as n grows.

    The interval is:

        mean(sample) +/- t_crit * SE

    where `t_crit = scipy.stats.t.ppf(q, df=n-1)` and `q` is the upper
    tail quantile matching `confidence` (e.g. `confidence=0.95` ->
    `q=0.975`, a two-sided interval).

    Args:
        sample: 1-D array of observed values, `n = len(sample) >= 2`.
        confidence: confidence level in (0, 1), e.g. 0.95 for a 95% CI.

    Returns:
        `(low, high)` -- the interval bounds as plain floats, `low <
        high`. `mean(sample)` is the interval's midpoint.

    Raises:
        Whatever numpy/scipy naturally raise for degenerate input (e.g.
        `n < 2`) -- no special-casing required for this task.
    """
    raise NotImplementedError


def ci_width_vs_sample_size(
    population: np.ndarray,
    sizes: list[int] = WIDTH_SIZES,
    confidence: float = 0.95,
    seed: int = SAMPLE_SEED,
    repeats: int = WIDTH_REPEATS,
) -> dict[int, float]:
    """Empirically show CI width shrinking as sample size grows.

    For each `n` in `sizes` (in the order given), draw `repeats`
    independent samples of size `n` from `population` (without
    replacement, drawn via a SINGLE `np.random.default_rng(seed)`
    instance that you create once at the top of this function and keep
    consuming across every draw -- outer loop over `sizes` in order,
    inner loop over `repeats` in order, so the draw sequence is fully
    determined by `seed`). For each draw, compute the CI width (`high -
    low` from `mean_confidence_interval`) and average the `repeats`
    widths for that `n`. Return `{n: mean_width}`.

    Averaging over repeats is what makes the 1/sqrt(n) law visible: a
    single sample's width is a noisy estimate (especially on a
    right-skewed population like this one), but the AVERAGE width over
    many independent draws converges to the theoretical expectation,
    which really does scale as roughly `1/sqrt(n)`.

    Args:
        population: 1-D array to sample from, e.g. `load_population()`'s
            return value.
        sizes: sample sizes to evaluate, in the order to draw them in.
        confidence: passed through to `mean_confidence_interval`.
        seed: seed for the single `default_rng` instance driving every
            draw (see above for the exact draw order this implies).
        repeats: number of independent samples drawn (and CI widths
            averaged) per size.

    Returns:
        Dict mapping each `n` in `sizes` to its average CI width (float).
        Widths should decrease monotonically as `n` increases, roughly
        proportional to `1/sqrt(n)` (e.g. doubling `n` should shrink the
        width by roughly a factor of `sqrt(2)`).
    """
    raise NotImplementedError


def make_figure(population: np.ndarray):
    """Build a matplotlib Figure supporting the width-vs-n claim.

    At minimum, produce a figure with:

    1. CI width vs. sample size -- a line/marker plot of the
       `ci_width_vs_sample_size(population)` result (x = n, y = mean CI
       width), visually showing the shrink as n grows.

    Optionally (recommended, a second subplot is fine): the fixed sample
    (`SAMPLE_SEED`, `SAMPLE_SIZE`) plotted as its mean with an error bar
    spanning `mean_confidence_interval`, against a reference line/marker
    at the true population mean (`population.mean()`) -- a visual check
    that the interval actually contains the number it's claiming to
    bracket.

    Args:
        population: 1-D array, e.g. `load_population()`'s return value.

    Returns:
        A `matplotlib.figure.Figure` with at least one Axes containing
        drawn content (lines/markers) -- not a bare, empty figure.
    """
    raise NotImplementedError
