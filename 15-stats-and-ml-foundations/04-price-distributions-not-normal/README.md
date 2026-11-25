# 04 -- Price Distributions Are Not Normal

## Backstory

Someone on the analytics team pulled the scraped price table, computed
`mean(price)` and `mean(price) +/- 2 * std(price)`, and shipped that as a
"typical price range, 95% confidence" slide to a client. Two things went
wrong immediately: the lower bound of the band was negative (a price can't
be negative), and the "typical" mean sat noticeably higher than what a
human skimming the raw prices would call typical -- a handful of
high-end electronics were dragging the average up.

Both symptoms have the same root cause: mean and standard deviation are
summaries built for symmetric, bell-shaped data. Real scraped prices are
not that shape -- they are heavily right-skewed, closer to log-normal than
normal. A cheap category has lots of items clustered near a typical price
and a long thin tail of expensive outliers; the mean gets pulled toward
that tail while the median doesn't. Reporting `mean +/- 2*std` on this kind
of data isn't just imprecise, it's actively misleading.

Your job: prove the raw price distribution isn't normal (don't just eyeball
it -- quantify it), show what "not normal" costs you concretely, and show
that a log transform is the right lens -- dramatically more symmetric, even
though it's never perfectly normal on this dataset (more on why below).

## What's given

- `src/distributions.py` -- three function stubs, each with a docstring
  that specifies the exact scipy calls to use (so your numbers and the
  validator's independently-recomputed numbers agree) and the exact rule
  for the one boolean judgment call in this task.
- The shared dataset at `../data/observations.parquet`, loaded via
  `harness.common.load_observations()`. "Valid prices" for this task means:
  `price` is not NaN, `price > 0`, and `currency == "USD"` -- filter for
  that yourself when you experiment; the validator does the same filtering
  before calling your functions.

## What's required

Implement all three functions in `src/distributions.py`:

1. `describe_distribution(prices)` -- skewness, excess kurtosis, and a
   normality-test p-value for a 1-D array of positive prices.
2. `log_makes_it_normal(prices)` -- the same three stats computed on both
   `prices` and `np.log(prices)`, plus a boolean verdict on whether the log
   transform is a meaningfully better fit to normality. The exact rule for
   that verdict is spelled out in the docstring -- read it before you
   guess at a threshold.
3. `make_figure(prices)` -- a matplotlib figure with at least two panels:
   a histogram of raw prices (it should look visibly right-skewed) and a
   histogram of log-prices (it should look close to symmetric by
   comparison). A Q-Q plot panel (`scipy.stats.probplot`) is encouraged but
   not required.

A subtlety worth sitting with before you write the boolean rule in
`log_makes_it_normal`: with tens of thousands of observations, a normality
test has enormous statistical power. It will report a p-value
indistinguishable from 0 on BOTH the raw prices and the log-transformed
prices -- because this dataset pools 8 categories with different median
prices and spreads into one array, so even log-prices form a mixture
distribution, not a single clean bell curve. That does not mean the log
transform "didn't work." Look at effect size (how much the skewness
actually shrinks), not just whether a hypothesis test's p-value crosses
0.05 -- at this sample size, it never will, on either scale.

## Completion criteria

From the module root:

```bash
uv run python 04-price-distributions-not-normal/tests/validate.py
```

The validator:

- Loads valid USD prices from the shared dataset and sanity-checks the data
  itself is significantly non-normal (this should always pass -- if it
  doesn't, the dataset is broken, not your code).
- Independently recomputes skewness, excess kurtosis, and normaltest
  p-value via scipy on both the raw and log-transformed prices, and grades
  your `describe_distribution` and `log_makes_it_normal` outputs against
  that reference within a float tolerance.
- Confirms your `log_is_more_normal` verdict is `True` and matches what the
  independently-recomputed rule also produces.
- Confirms `make_figure` returns a real, multi-panel figure with drawn
  content via `require_figure`.

`PASSED` prints the measured raw vs. log skewness and p-values. Visual
correctness of the figure (labels, bin choice, whether it's actually
readable) is not something the validator can grade -- that's on you to get
right for your own understanding.

## Estimated evenings

1-2

## Topics to read up on

- Skewness and kurtosis as distribution-shape summaries, and what a
  positive vs. negative value of each means
- The log-normal distribution -- why "log of the data is normal" shows up
  so often for prices, incomes, file sizes, and other quantities that can't
  go negative and are driven by multiplicative rather than additive effects
- Normality tests: D'Agostino and Pearson's K^2 test (`scipy.stats.
  normaltest`) -- what its null hypothesis is, and why statistical power
  scales with sample size (why a huge dataset can reject normality even
  when the departure is practically small)
- Q-Q (quantile-quantile) plots as a visual normality check that doesn't
  collapse to a single p-value
- Why mean and standard deviation are the wrong summary statistics for
  skewed data, and what to report instead (median, percentiles, geometric
  mean)
- Log transforms: why they compress a multiplicative right tail into
  something closer to additive/symmetric, and their limits (a mixture of
  differently-scaled sub-populations stays a mixture even after transform)

## Off-limits

`.authoring/design.md` at the module root documents the harness API, the
dataset's exact generation process, and the committed ground-truth values --
spoilers. Don't read it before finishing this task.
