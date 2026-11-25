# 06 -- Confidence Intervals

## Backstory

A client scraped 200 electronics listing pages, averaged the prices, and
emailed you one number: "the average price is $X." Then they asked the
question that actually matters: "how sure are you?" $X is a single number
computed from a single sample -- scrape a different 200 pages and you'd get
a slightly different average. Reporting the mean alone pretends that
sampling noise doesn't exist. Reporting a confidence interval says, honestly,
"the true average is very likely somewhere in this range, and here's how
wide that range is." The client's next question is always "how many more
pages would it take to cut that range in half?" -- and the answer follows a
clean, checkable law.

## What's given

- `src/ci.py` -- the scaffold you implement, plus `load_population()`,
  which is **given, fully implemented, do not modify**. It reconstructs the
  full observation set exactly the way `generate.py` built it and returns
  every valid USD price (no parsing defects, no non-USD currency) for
  `CATEGORY = "electronics"` as a 1-D array. Data-quality filtering is not
  this task's subject -- that array is your clean population to sample
  from.
- A **fixed sampling recipe**, so your numbers and the validator's numbers
  are computed from the identical sample:

  ```python
  population = load_population()          # CATEGORY = "electronics"
  rng = np.random.default_rng(SAMPLE_SEED)  # SAMPLE_SEED = 20240718
  idx = rng.choice(len(population), size=SAMPLE_SIZE, replace=False)  # SAMPLE_SIZE = 200
  sample = population[idx]
  ```

  This exact recipe (build/receive the population, then
  `np.random.default_rng(seed).choice(len(population), size=n,
  replace=False)`) is reused everywhere a `seed` argument appears in this
  task -- same order of operations every time, so every draw reproduces
  bit-for-bit.
- `WIDTH_SIZES = [50, 100, 200, 400, 800]` and `WIDTH_REPEATS = 100` --
  constants controlling the width-vs-sample-size sweep (see below for why
  `WIDTH_REPEATS` exists).

## What's required

Implement three functions in `src/ci.py`:

1. **`mean_confidence_interval(sample, confidence=0.95) -> (low, high)`** --
   a Student t confidence interval for the sample mean: `mean +/- t_crit *
   SE`, where `SE` is the standard error of the mean and `t_crit` comes
   from the t distribution with `n - 1` degrees of freedom (`scipy.stats.
   t.ppf`), not the normal distribution. At `n=200` the difference between
   t and z is tiny; at small n it isn't -- this task grades both regimes.

2. **`ci_width_vs_sample_size(population, sizes, confidence, seed, repeats)
   -> {n: width}`** -- for each `n` in `sizes`, draw `repeats` independent
   samples of size `n` (all draws consuming a single `default_rng(seed)`
   instance you create once, outer loop over `sizes` in order, inner loop
   over `repeats` in order) and average their CI widths. Why average
   instead of drawing once per `n`? The electronics price population is
   right-skewed with a real long tail -- a single sample's width is a
   noisy estimate of the *expected* width, and one unlucky high-price draw
   can make a single n=200 sample's CI wider than a single n=50 sample's.
   Averaging over many independent draws converges to the theoretical
   width, which really does shrink as roughly `1/sqrt(n)`. This is
   standard Monte Carlo practice, not a trick to dodge a hard case.

3. **`make_figure(population) -> matplotlib.figure.Figure`** -- at least a
   plot of CI width vs. sample size showing the shrink; a second panel
   showing the fixed sample's mean with its error bar against the true
   population mean is recommended but not required.

## Completion criteria

From this task's directory (or the module root, adjusting the path):

```bash
uv run python tests/validate.py
```

The validator recomputes every reference value itself via scipy -- it
never grades your `mean_confidence_interval` against itself. It checks, in
order: your CI on the fixed `n=200` sample matches the scipy reference
within a tight float tolerance; that CI actually contains the true
population mean (verified while authoring this task -- holds for the
pinned seed); the same function on a second, small (`n=15`) fixed sample,
where a t-vs-z mistake produces a large, easily-caught discrepancy;
`ci_width_vs_sample_size`'s returned widths against an independently
computed reference, plus a direct check that the widths decrease
monotonically and that `width(50) / width(200)` lands near the theoretical
`sqrt(200/50) = 2.0`; and finally that `make_figure` produces a real,
non-empty figure. `PASSED` prints your CI and the width ratio; anything
unfinished or wrong prints one `NOT PASSED: <reason>` line and exits 1 --
no tracebacks.

## Estimated evenings

1-2

## Topics to read up on

- Standard error of the mean, and how it differs from the standard
  deviation of the data itself
- Student's t distribution vs. the normal distribution -- why small samples
  need the wider, fatter-tailed t critical value, and why the gap between
  them shrinks as degrees of freedom grow
- What a 95% confidence interval actually means (and what it doesn't -- it
  is not "95% probability the true mean is in this specific interval")
- The 1/sqrt(n) precision law and its practical consequence: to halve a
  CI's width, you need roughly 4x the sample size
- Sample vs. population, and why estimating a population's standard
  deviation from a sample changes which distribution is correct

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the dataset's exact defect mechanics, and this task's
verification margins -- spoilers. Don't read it before finishing this
task.
