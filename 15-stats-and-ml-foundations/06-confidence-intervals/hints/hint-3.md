`mean_confidence_interval`:

1. `n = len(sample)`, `mean = sample.mean()`.
2. `sem = scipy.stats.sem(sample)` (defaults to `ddof=1`, which is what you
   want).
3. Two-sided `confidence` interval needs the upper-tail quantile
   `q = 1 - (1 - confidence) / 2` (for `confidence=0.95`, `q=0.975`).
4. `t_crit = scipy.stats.t.ppf(q, df=n - 1)`.
5. `margin = t_crit * sem`; return `(mean - margin, mean + margin)`.

Sanity check while developing: at `n=200`, `t_crit` should come out very
close to `1.96` (the familiar normal 95% value) -- if it's noticeably
different, check your `df` argument. At a much smaller `n` (try slicing
the fixed sample down to its first 15 entries), `t_crit` should be
noticeably *larger* than `1.96` -- if it isn't moving at all as `n`
shrinks, you're accidentally using a fixed z-value somewhere instead of
`t.ppf`.

`ci_width_vs_sample_size`:

1. Create exactly one `rng = np.random.default_rng(seed)` at the top of
   the function -- not one per size, not one per repeat.
2. Loop over `sizes` in the order given (a plain `for n in sizes:`).
3. Inside that, loop `repeats` times: `idx = rng.choice(len(population),
   size=n, replace=False)`, build `sample = population[idx]`, call your
   own `mean_confidence_interval(sample, confidence)`, compute `high -
   low`, and collect it.
4. After the inner loop, `widths_dict[n] = float(np.mean(collected))`.
5. Return `widths_dict` once all sizes are done.

The two loops must be nested in exactly this order (sizes outer, repeats
inner) reusing the same `rng` object throughout -- that's what makes the
sequence of draws, and therefore the final numbers, fully determined by
`seed`. If you instead created a fresh `default_rng(seed)` inside the
inner loop, every repeat would draw the identical sample, and averaging
would do nothing.

`make_figure`: call `ci_width_vs_sample_size(population)` once, then
`ax.plot(list(result.keys()), list(result.values()), marker="o")` (a log
scale on the x-axis, `ax.set_xscale("log")`, makes the `1/sqrt(n)` shape
easier to see). For the optional second panel, use `ax.errorbar` with a
single x position, the fixed sample's mean as `y`, and
`yerr` built from half the CI width (`(high - low) / 2`), plus
`ax.axhline(population.mean())` as the reference line.
