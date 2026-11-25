"""t04 -- price distributions are not normal.

Real scraped prices are heavily right-skewed / approximately log-normal: a
few very expensive electronics drag a long right tail, while the bulk of
observations cluster around a typical category price. Reporting "mean
price" and a "mean +/- 2 std dev" band on data shaped like this is
misleading -- the mean is pulled toward the tail, and a symmetric +/-2
sigma band either dips into impossible negative prices or misses the tail
it was supposed to describe.

This task: quantify how non-normal the raw price distribution is, show that
a log transform makes it dramatically closer to normal (never PERFECTLY
normal -- this dataset mixes 8 categories with different medians/spreads
and includes a genuine outlier tail on top of each category's log-normal
draw, so log-prices are a mixture, not a single clean bell curve -- but the
effect size collapses by well over an order of magnitude), and produce a
figure that makes the shape visible.

Every function below MUST use these exact scipy calls, so the validator
(which recomputes the same three statistics independently on the same
input array) agrees with your numbers:

  - skewness:           scipy.stats.skew(x)              (default bias=True)
  - excess kurtosis:    scipy.stats.kurtosis(x)           (default fisher=True, bias=True)
  - normaltest p-value: scipy.stats.normaltest(x).pvalue  (D'Agostino-Pearson K^2 test)

`x` is always a 1-D array of positive, finite prices -- no NaNs, no
zeros/negatives, already filtered to a single currency. Callers (the
validator, and your own testing) are responsible for that filtering; these
functions do not filter anything themselves.
"""

import numpy as np


def describe_distribution(prices: np.ndarray) -> dict:
    """Summarize how normal (or not) a 1-D array of positive prices is.

    Args:
        prices: 1-D numpy array of positive, finite floats.

    Returns:
        dict with exactly these three keys:
          - "skewness": float, scipy.stats.skew(prices)
          - "excess_kurtosis": float, scipy.stats.kurtosis(prices)
          - "normaltest_pvalue": float, scipy.stats.normaltest(prices).pvalue

        A normal distribution has skewness 0 and excess kurtosis 0.
        Positive skewness means a long right tail (a handful of expensive
        outliers pull the mean above the median) -- expect a strongly
        positive number here for raw scraped prices. Positive excess
        kurtosis means fatter tails / a sharper peak than a normal
        distribution ("leptokurtic").

        `normaltest` is D'Agostino and Pearson's test: the null hypothesis
        is "this sample was drawn from a normal distribution"; a very small
        p-value is strong evidence AGAINST that null. With tens of
        thousands of observations this test has enormous statistical
        power -- expect a p-value indistinguishable from 0 for the raw
        prices.
    """
    raise NotImplementedError


def log_makes_it_normal(prices: np.ndarray) -> dict:
    """Compare the raw price distribution to its log transform, using the
    same three statistics as `describe_distribution`, and decide whether
    the log transform is a meaningfully better fit to normality.

    Args:
        prices: 1-D numpy array of positive, finite floats.

    Returns:
        dict with exactly these three keys:
          - "raw": describe_distribution(prices)
          - "log": describe_distribution(np.log(prices))
          - "log_is_more_normal": bool, per the rule below

        Rule for "log_is_more_normal" -- both conditions must hold:

        1. Skewness collapses by more than a factor of 5:
               abs(log["skewness"]) < 0.2 * abs(raw["skewness"])
        2. The log-scale normaltest p-value is not smaller than the
           raw-scale one:
               log["normaltest_pvalue"] >= raw["normaltest_pvalue"]

        Why ">=" and not a strict "greater than": at the sample sizes this
        dataset uses (tens of thousands of rows), `normaltest`'s p-value
        underflows to exactly 0.0 on BOTH scales -- real-world data is
        never perfectly normal, and with enough observations the test
        rejects normality regardless of how good the fit looks by eye.
        That is a genuine, important property of large-sample hypothesis
        tests, not a bug in this task: with huge N, any departure from
        exact normality becomes "significant," so the p-value alone stops
        being a useful discriminator and effect size (condition 1, the
        skewness ratio) carries the argument. Condition 2 is a
        non-regression check -- log-transforming must not make the
        normality evidence WORSE -- not the deciding signal.
    """
    raise NotImplementedError


def make_figure(prices: np.ndarray):
    """Build a matplotlib Figure with at least 2 panels showing the raw vs.
    log-transformed price distribution.

    Args:
        prices: 1-D numpy array of positive, finite floats.

    Returns:
        matplotlib.figure.Figure with at least 2 Axes, each with actual
        drawn content (a blank Axes does not satisfy the validator).
        Suggested layout (not enforced structurally beyond axis count +
        drawn content):

          - Panel 1: histogram of raw `prices` -- should look visibly
            right-skewed (long tail to the right, most mass piled on the
            left near typical prices).
          - Panel 2: histogram of `np.log(prices)` -- should look close to
            symmetric / bell-shaped by comparison.
          - Optional panel 3: a Q-Q plot of `np.log(prices)` against a
            normal distribution (`scipy.stats.probplot(np.log(prices),
            dist="norm", plot=ax)`) -- points falling close to the
            reference line are visual evidence of near-normality;
            systematic curvature in the tails shows where log-prices still
            aren't quite normal (the mixture-of-categories effect).

        Do not call plt.show(). Return the Figure object itself, e.g. via
        `fig, axes = plt.subplots(1, 2, figsize=(...))` or
        `matplotlib.figure.Figure()` + `fig.add_subplot(...)`.
    """
    raise NotImplementedError
