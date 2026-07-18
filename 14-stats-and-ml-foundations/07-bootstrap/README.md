# 07 -- Bootstrap

## Backstory

You report the median price in a category to a client. They ask for error
bars: "how confident are you in that number?" For the mean, task 06 gave
you a clean answer -- the t-interval, backed by a formula for the standard
error of a mean that's been in every stats textbook for a century. You go
looking for the equivalent formula for a MEDIAN and come up empty. There
isn't one -- not a simple one, anyway. The sampling distribution of a
median depends on the shape of the data in a way that doesn't reduce to a
plug-in standard-error expression the way a mean's does. Same problem for
a 90th percentile, or a ratio of two medians, or almost any statistic that
isn't a straightforward sum.

The fix doesn't require deriving new theory: you resample your own data.
Draw a new sample the same size as yours, WITH replacement, from your own
data; recompute the median; do that a couple thousand times; look at the
spread. That spread IS your uncertainty, no formula required, and it works
for (almost) any statistic you can write as a function of a sample --
median, percentile, ratio, whatever. This is the bootstrap, and this task
has you build the plumbing (bootstrap resampling loop, percentile CI) and
point it at the median of scraped USD prices, where the t-interval doesn't
apply.

## What's given

- `src/bootstrap.py` -- the scaffold. Two pieces:
  - **Provided, not a stub** -- `load_valid_usd_prices()` (filters
    `load_observations()` down to rows with `currency == "USD"`, a
    non-NaN `price`, and `price > 0`) and `draw_base_sample()` (draws
    `SAMPLE_SIZE` of those, once, without replacement, seeded by
    `SAMPLE_SEED`). You don't need to touch either.
  - **Constants, pinned so your numbers and the validator's numbers
    agree**:
    ```python
    SAMPLE_SEED = 20260718
    SAMPLE_SIZE = 300
    BOOTSTRAP_SEED = 12345
    N_RESAMPLES = 2000
    CONFIDENCE = 0.95
    STATISTIC = np.median
    ```
  - **Four stubs you implement** -- `bootstrap_distribution`,
    `percentile_ci`, `bootstrap_ci`, `make_figure`. Every stub has a full
    docstring spelling out its contract; no reference code anywhere in
    this repository, in the hints or otherwise.

### The pinned resampling recipe

This is the exact procedure the validator reproduces independently to
build its reference numbers. Follow it precisely and your results will
land very close to the validator's; deviate (wrong replacement mode,
re-seeded rng inside the loop, wrong percentile bounds) and they won't.

1. **Base sample** (already done for you): from every valid USD price in
   `load_observations()`, draw `SAMPLE_SIZE = 300` of them ONCE, WITHOUT
   replacement, via `np.random.default_rng(SAMPLE_SEED).choice(n, size=
   SAMPLE_SIZE, replace=False)`. This fixed array is "your sample" -- the
   one dataset an analyst actually has. Everything below resamples FROM
   it; it never touches the full population again.
2. **Bootstrap resampling** (you implement this): create exactly ONE
   `rng = np.random.default_rng(BOOTSTRAP_SEED)` before any looping. Then,
   `N_RESAMPLES = 2000` times: draw `idx = rng.integers(0, n, size=n)`
   where `n = len(sample)` -- WITH replacement, so indices repeat and some
   original points are skipped in any given resample -- and compute
   `STATISTIC(sample[idx])` (the median). Collect all `N_RESAMPLES`
   results into an array.
3. **Percentile CI**: at `CONFIDENCE = 0.95`, take the 2.5th and 97.5th
   percentiles of that array of `N_RESAMPLES` statistics, via
   `np.percentile` with its default (linear) interpolation. Those two
   numbers are your confidence interval.

That's the whole method -- no closed-form standard error, no normality
assumption about the median itself. The only assumption is that your
sample is a reasonable stand-in for the population it came from.

## What's required

Implement all four functions in `src/bootstrap.py`:

- `bootstrap_distribution(sample, statistic_fn, n_resamples, seed)` --
  the resampling loop from step 2 above, generalized to any
  `statistic_fn`.
- `percentile_ci(boot_stats, confidence)` -- step 3, generalized to any
  confidence level.
- `bootstrap_ci(sample, statistic_fn, n_resamples, confidence, seed)` --
  a convenience wrapper combining the two above.
- `make_figure(boot_stats, ci)` -- a histogram of the bootstrap
  distribution with the two CI bounds marked as vertical lines, plus the
  point estimate marked distinctly from the CI bounds.

## Completion criteria

```bash
cd 14-stats-and-ml-foundations
uv run python 07-bootstrap/tests/validate.py
```

The validator independently rebuilds the base sample and the reference
bootstrap distribution/CI using the pinned recipe above (never by calling
your code for its own reference values), then grades your four functions
against that reference:

- `bootstrap_distribution` must reproduce the reference array closely and
  have length `N_RESAMPLES`, with a spread (`std`) in a sane range --
  neither collapsed to a point nor blown up.
- `percentile_ci` must reproduce the reference bounds from the same
  bootstrap array.
- `bootstrap_ci` (the number `PASSED` reports) is graded with a modest
  relative tolerance (`1e-3`) against the reference CI -- loose enough to
  absorb float-ordering noise, tight enough to reject a recipe that
  drifted from the one pinned above.
- The CI must be a proper interval: it has to bracket both your sample's
  own point estimate AND the TRUE population median (computed directly
  over every valid USD price in the dataset, independent of any sampling
  or resampling). With the pinned seeds this holds; if your CI misses the
  population median, something in the recipe drifted.
- `make_figure` must return a real, drawn-on `matplotlib.figure.Figure`
  (checked structurally -- content and labeling quality are on you).

`PASSED` prints the CI, the point estimate, the population median, and
the bootstrap distribution's spread. `NOT PASSED: <reason>` and a nonzero
exit otherwise, no raw traceback.

## Estimated evenings

1-2

## Topics to read up on

- The bootstrap principle: your sample stands in for the population; you
  resample FROM your sample (not the population) to approximate how much
  your statistic would vary if you'd drawn a different sample
- Resampling WITH replacement, and why that specific choice (versus,
  e.g., re-drawing without replacement) is what makes the resamples vary
  at all
- The percentile method for a bootstrap CI, and its known limitations
  (bias for skewed statistics, coverage that isn't exactly nominal for
  small samples) versus fancier variants (BCa, the bootstrap-t) that this
  task doesn't ask you to implement
- Why the median (and percentiles generally) lack a simple closed-form
  standard error the way a mean does -- and why a naive t-interval built
  around the median's point estimate would be the wrong tool: it assumes
  a sampling distribution shape (normal, characterized by one SE number)
  that the median's actual sampling distribution doesn't reliably have
- Bootstrap assumptions and failure modes: it assumes your sample is
  reasonably representative and i.i.d.; it breaks down for very small
  samples, for statistics sensitive to the extreme tail (e.g. a max), and
  under strong dependence between observations (time-series
  autocorrelation, clustered sampling) where naive resampling doesn't
  preserve the structure that generated the original variability

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the dataset schema, and the exact generation recipe --
spoilers. Don't read it before finishing this task.
