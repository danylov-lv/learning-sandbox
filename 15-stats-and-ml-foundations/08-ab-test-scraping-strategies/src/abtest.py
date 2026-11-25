"""t08 -- A/B test: is strategy B's higher extraction rate real, or noise?

Implement three functions below: `two_proportion_test`, `interpret`, and
`make_figure`. Together they answer the bake-off question from this task's
README: strategy A (plain HTTP) and strategy B (HTTP + retry/headless
fallback) each attempted to extract a required field from a batch of pages;
B succeeded more often; is that gap real, or could it be sampling noise from
running each strategy on a finite batch of pages?

You are given `a` and `b`: bool numpy arrays (see `src/experiment.py`,
fully implemented, not yours to edit), one entry per attempt, True where the
field was successfully extracted. `a` and `b` may have different lengths.
You do NOT get to see the true generating probabilities -- only the
observed outcomes, the same as you would with real logged results.

## The test: pooled two-proportion z-test

This is a standard, well-defined statistical test -- look it up if the name
alone isn't enough (search "two-proportion z-test", "pooled proportion
test"). The core idea, restated here so the shape of the computation is
unambiguous:

Under the null hypothesis ("no real difference between A and B's true
success rates"), if that were true, the best single estimate of the shared
success rate is the POOLED proportion across both samples combined -- not
either group's proportion alone. The test asks: given that pooled estimate
and the two sample sizes, how far out in the tails is the OBSERVED gap
between p_a and p_b? A gap that would be common under "no real difference"
is unremarkable; a gap that would be rare is evidence the difference is
real.

`p_value` must be a proper two-sided p-value from the standard normal CDF
(`scipy.stats.norm.cdf`), not a one-sided one and not a chi-squared
approximation -- the validator recomputes the same pooled z-test
independently and checks your numbers against it.

Effect size is a SEPARATE concept from the p-value: the p-value tells you
how confident you can be that a difference exists at all; effect size
(here: the raw proportion gap, and/or the relative lift) tells you how BIG
that difference is. A tiny, practically irrelevant gap can still produce a
tiny p-value if the sample is large enough -- report both, don't collapse
them into one number.

## What to implement

- `two_proportion_test(a, b) -> dict` with keys:
    - "p_a": float, observed success proportion in `a` (mean of the bool array)
    - "p_b": float, observed success proportion in `b`
    - "diff": float, p_b - p_a (signed: positive means B beat A)
    - "z": float, the pooled two-proportion z-statistic
    - "p_value": float, the two-sided p-value for that z-statistic
    - "relative_lift": float, diff / p_a -- B's improvement over A as a
      fraction of A's rate (e.g. 0.10 means "B is 10% better, relatively,
      than A")

- `interpret(result, alpha=0.05) -> dict` with keys:
    - "significant": bool, True iff result["p_value"] < alpha
    - "reject_null": bool, same value as "significant" (the decision is the
      same thing stated two ways -- rejecting the null IS what
      "significant at alpha" means here)
    - "verdict": a short human-readable string summarizing the decision
      (e.g. mentioning whether the observed gap is likely real or
      consistent with noise at this alpha). Content isn't graded beyond
      being present and non-empty; the boolean fields are what's checked.

- `make_figure(a, b, result) -> matplotlib.figure.Figure` -- a bar (or
  point) chart with TWO bars/points, one per strategy, height/position =
  observed proportion, with a 95% confidence-interval error bar on EACH
  proportion separately (Wald or Wilson -- your choice; document which one
  you used in a code comment). The point of the figure is to make the
  overlap-or-separation between A's and B's CIs visually obvious -- when
  the error bars don't overlap, the eye already suspects what the p-value
  will confirm; when they do overlap heavily, that's a visual cue toward
  "not significant" even before running the test. Label both axes and give
  the figure a title. Use a non-interactive backend (`Agg`) and do not call
  `plt.show()`.

Do not import `statsmodels` -- it isn't a dependency of this module.
Everything here is implementable directly from `numpy` and
`scipy.stats.norm`.
"""


def two_proportion_test(a, b):
    """Pooled two-proportion z-test comparing two bool arrays of successes.

    Args:
        a: 1-D bool (or 0/1) array-like, strategy A's per-attempt outcomes.
        b: 1-D bool (or 0/1) array-like, strategy B's per-attempt outcomes.

    Returns:
        dict with keys "p_a", "p_b", "diff", "z", "p_value", "relative_lift"
        as described in the module docstring above.
    """
    raise NotImplementedError


def interpret(result, alpha=0.05):
    """Turn a `two_proportion_test` result into a significance decision.

    Args:
        result: the dict returned by `two_proportion_test`.
        alpha: significance threshold (default 0.05).

    Returns:
        dict with keys "significant" (bool), "reject_null" (bool, same
        value as "significant"), and "verdict" (short non-empty string).
    """
    raise NotImplementedError


def make_figure(a, b, result):
    """Build a 2-bar (or 2-point) figure comparing A's and B's observed
    proportions with 95% CI error bars on each.

    Args:
        a: strategy A's bool outcome array.
        b: strategy B's bool outcome array.
        result: the dict returned by `two_proportion_test` (for the
            observed p_a/p_b -- recompute the CIs yourself, they are not
            part of that dict).

    Returns:
        A `matplotlib.figure.Figure` with at least one Axes carrying drawn
        content (two bars/points plus their error bars), a title, and axis
        labels.
    """
    raise NotImplementedError
