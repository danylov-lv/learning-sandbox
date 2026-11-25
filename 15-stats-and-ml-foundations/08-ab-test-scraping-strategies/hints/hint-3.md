Concrete shape of the computation, in prose (no code -- translating this
into numpy/scipy calls is the task):

**`two_proportion_test(a, b)`**

- `n_a = len(a)`, `n_b = len(b)`; `p_a = a.mean()`, `p_b = b.mean()` (a bool
  array's mean is exactly the proportion of `True`s -- no separate success
  count needed).
- `diff = p_b - p_a`.
- Pooled proportion: `p_pool = (number of successes in a + number of
  successes in b) / (n_a + n_b)`. Note this is NOT `(p_a + p_b) / 2` unless
  `n_a == n_b` exactly -- it's a weighted pool by raw counts, which happens
  to coincide with the simple average only when the two sample sizes match.
- Pooled standard error: `se = sqrt(p_pool * (1 - p_pool) * (1/n_a +
  1/n_b))`.
- `z = diff / se`.
- Two-sided p-value: `p_value = 2 * (1 - norm.cdf(abs(z)))`, using
  `scipy.stats.norm` (standard normal, mean 0, std 1 -- the default
  parameters). Equivalently `2 * norm.sf(abs(z))` if you prefer the
  survival function.
- `relative_lift = diff / p_a`.

**`interpret(result, alpha=0.05)`**

- `significant = result["p_value"] < alpha`.
- `reject_null` is the same boolean as `significant` -- they're two names
  for the same decision in this framing (reject the null of "no
  difference" exactly when the result clears the significance bar).
- `verdict`: a short string. Worth having it actually say something
  different depending on the boolean, e.g. naming the observed diff and
  whether it looks like real signal or noise at this alpha -- but the
  validator only checks that it's a non-empty string, not its exact
  wording.

**`make_figure(a, b, result)`**

- Two bars or two points, x-positions "A" and "B" (or 0 and 1), heights/
  y-values `result["p_a"]` and `result["p_b"]`.
- A 95% CI per group: Wald is the simplest to get right --
  `p ± 1.96 * sqrt(p * (1 - p) / n)` for each group's own `p` and `n`
  (`1.96` is the standard normal's ~97.5th percentile, or pull it from
  `scipy.stats.norm.ppf(0.975)` if you'd rather not hardcode it). Wilson is
  more accurate at extreme proportions or small `n` if you want to look it
  up, but isn't required here -- your choice, just note which one you used.
- Plot the CI as an error bar (`ax.errorbar` or `ax.bar` + `yerr=`) on each
  point/bar. Label both axes, give the figure/axes a title, use a
  non-interactive backend, no `plt.show()`.
