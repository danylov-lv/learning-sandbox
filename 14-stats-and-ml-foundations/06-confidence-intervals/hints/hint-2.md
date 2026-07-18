The interval is `mean +/- margin`, where `margin = critical_value *
standard_error`. Two things determine the margin's size:

- **The standard error** itself: `s / sqrt(n)`, where `s` is the sample's
  standard deviation with `ddof=1` (divide by `n - 1`, not `n` -- this is
  what makes the estimator unbiased for the population variance).
  `scipy.stats.sem` computes exactly this by default; you can also build it
  from `np.std(sample, ddof=1) / np.sqrt(len(sample))` if you want to see
  the pieces.
- **The critical value**: because you don't actually know the population's
  true standard deviation -- you're estimating it from the same sample --
  the correct sampling distribution for the standardized mean is Student's
  t with `n - 1` degrees of freedom, not the normal distribution. At small
  `n`, t has fatter tails than normal (to account for the extra
  uncertainty from estimating the variance too), so its critical value is
  larger; as `n` grows, t converges to normal and the gap disappears. Look
  at `scipy.stats.t.ppf` and think about which quantile a two-sided 95%
  interval needs (it isn't 0.95).

For the width-vs-n sweep: the reason a single sample per `n` won't cleanly
show `1/sqrt(n)` on this dataset is that the population is right-skewed --
some samples get unlucky and include a relatively expensive item, inflating
that one sample's variance (and therefore its CI width) well past what
`1/sqrt(n)` alone would predict. Averaging many independent samples' widths
at each `n` is what makes the underlying `1/sqrt(n)` trend visible instead
of buried in that noise. Think of it as Monte Carlo estimation of the
*expected* width, not a single realization of it.
