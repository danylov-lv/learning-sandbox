The three scipy calls, spelled out (all in `scipy.stats`), matching what
the validator independently recomputes:

- `skew(x)` -- call it with just the array, no extra keyword arguments.
  Its default `bias=True` is what you want; don't pass `bias=False`.
- `kurtosis(x)` -- same, call it with just the array. Its defaults are
  `fisher=True` (reports EXCESS kurtosis, i.e. a normal distribution scores
  0 -- this is the convention the task wants) and `bias=True`. Don't
  override either.
- `normaltest(x)` -- this returns an object with both a `.statistic` and a
  `.pvalue` attribute; the task only needs `.pvalue`.

`describe_distribution` is a thin wrapper: call all three on the input
array, put the three results in a dict under the keys `"skewness"`,
`"excess_kurtosis"`, `"normaltest_pvalue"`. Nothing more.

`log_makes_it_normal` calls `describe_distribution` twice -- once on
`prices`, once on `np.log(prices)` -- and packages both results plus a
boolean under `"raw"`, `"log"`, and `"log_is_more_normal"`.

The boolean itself, concretely: pull `raw_skew = raw["skewness"]` and
`log_skew = log["skewness"]` (and similarly the two p-values) out of the
two dicts you just built. `log_is_more_normal` is `True` exactly when BOTH:

- `abs(log_skew)` is under one-fifth of `abs(raw_skew)` -- i.e.
  `abs(log_skew) < 0.2 * abs(raw_skew)`. On this dataset the raw skewness
  is in the double digits and the log skewness is close to 1 -- the ratio
  is nowhere near the 0.2 boundary, so you don't need to fight over
  precision here, just implement the comparison correctly.
- the log-scale p-value is `>=` the raw-scale p-value (not strictly
  greater -- both routinely come back as exactly `0.0` at this sample size,
  and `0.0 >= 0.0` should still count as "didn't get worse").

For `make_figure`: build a `Figure` with 2 (or 3) `Axes` via `plt.
subplots(1, 2, ...)` or equivalent. Panel 1: `ax.hist(prices, bins=...)`.
Panel 2: `ax.hist(np.log(prices), bins=...)`. If you add a third panel,
`scipy.stats.probplot(np.log(prices), dist="norm", plot=ax3)` draws
directly onto an Axes you hand it via the `plot=` keyword. Give each axis a
title so you (not the validator) can tell them apart later. Return the
`Figure` object -- `fig`, not `plt` and not `None` -- and don't call
`plt.show()`.
