# 08 -- A/B Test: Scraping Strategies

## Backstory

Your scraper's field-extraction step has two implementations sitting side
by side in the codebase. Strategy A is the original: one plain HTTP GET,
parse the response, done. Cheap, fast, and it's been running in production
for months. Strategy B is what a teammate built last sprint: same GET
first, but when the field isn't found, it falls back to a retrying,
headless-browser render before giving up -- catching pages that need
JavaScript to populate the field, or that flaked on the first attempt.
Strategy B is slower and burns more compute per page; running it at full
scale costs real money in headless-browser time.

To decide whether B is worth shipping, you ran a bake-off: 1500 pages
through strategy A, 1500 different pages through strategy B, and logged
whether each attempt successfully extracted the field. Strategy B came out
ahead -- a noticeably higher hit rate. But 1500 attempts is a finite
sample, and any finite sample has noise. Before you tell your team "ship B,
it's better," you need an answer to a sharper question: is that gap the
kind of thing that would show up reliably if you ran the bake-off again, or
is it plausibly just how this particular batch of 1500-vs-1500 pages
happened to fall? And separately -- even if it's real, is it big enough to
be worth what B costs?

This is exactly the situation a hypothesis test exists for. You're not
asking "did B do better on this sample" (yes, trivially, by inspection).
You're asking "how surprising would this gap be if A and B actually had the
same true success rate, and I just got unlucky/lucky sampling?" A
two-proportion z-test turns that question into a number.

## What's given

- `src/experiment.py` -- fully implemented, not yours to edit.
  `simulate_experiment(seed=...)` draws two independent batches of
  Bernoulli trials (bool numpy arrays `a` and `b`, one entry per attempt,
  `True` = field extracted) from fixed true success probabilities, using
  `np.random.default_rng(seed)`. The docstring documents the true
  parameters -- they're the ground truth this task's validator uses to
  confirm the bake-off has a detectable effect at the default seed, not
  something your own test gets to read. A second function,
  `simulate_null_experiment`, gives you a much smaller (150-vs-150)
  version of the same true gap, for your own exploration of what happens
  to significance when the sample shrinks (not graded).
- `src/abtest.py` -- three function stubs (`two_proportion_test`,
  `interpret`, `make_figure`), each `raise NotImplementedError` with a
  docstring spelling out the exact statistical test to implement (a pooled
  two-proportion z-test) and the exact keys each function must return.

## What's required

Implement all three functions in `src/abtest.py`:

1. **`two_proportion_test(a, b) -> dict`** -- the pooled two-proportion
   z-test. Compute each strategy's observed proportion, the signed
   difference, the pooled z-statistic, a two-sided p-value (from the
   standard normal CDF, not a chi-squared approximation), and the relative
   lift (the gap as a fraction of A's rate). See the docstring for exact
   key names.
2. **`interpret(result, alpha=0.05) -> dict`** -- turn the test result into
   a significance decision: is the p-value below alpha, and what does that
   mean in plain language.
3. **`make_figure(a, b, result) -> matplotlib.figure.Figure`** -- a 2-bar
   (or 2-point) chart of the two observed proportions, each with a 95%
   confidence-interval error bar, so the reader can see at a glance whether
   the two intervals overlap or are cleanly separated.

`statsmodels` is not a dependency of this module -- everything here is
directly implementable from `numpy` and `scipy.stats.norm`.

## Completion criteria

```bash
cd 14-stats-and-ml-foundations
uv run python 08-ab-test-scraping-strategies/tests/validate.py
```

The validator calls `simulate_experiment()` at its default (pinned) seed,
independently recomputes the pooled two-proportion z-test on the same `a`,
`b` arrays via `scipy.stats.norm`, and checks your `two_proportion_test`
output against that reference within a float tolerance (p-value gets a
slightly looser tolerance than the other fields -- it's the most sensitive
quantity in the computation). It also checks that your `interpret` reaches
the same significant/reject_null decision the reference does (at the
default seed, the gap is comfortably significant, by design, so this
exercises the "significant" branch deterministically), and that
`make_figure` returns a Figure with real drawn content. Prints
`PASSED: ...` with the observed p_a, p_b, diff, z, and p_value, or
`NOT PASSED: <reason>` and exits 1 -- including while the stub still
raises `NotImplementedError`.

## Estimated evenings

1-2

## Topics to read up on

- Null hypothesis significance testing: what the null hypothesis is, and
  what a p-value does and doesn't measure (it is NOT "the probability the
  null hypothesis is true")
- The two-proportion z-test, specifically the pooled-proportion version
  (why you pool under the null rather than using each sample's own
  proportion for the standard error)
- The standard normal CDF and how it turns a z-statistic into a two-sided
  p-value
- Effect size vs. statistical significance -- why they answer different
  questions, and why a result can be highly significant and practically
  tiny (or the reverse: a large gap that isn't significant, in a small
  sample)
- Type I and Type II error, and statistical power -- what alpha actually
  controls, and what determines whether a real effect gets detected
- Why increasing sample size makes smaller and smaller true differences
  "statistically significant" -- and what that implies for reading a
  p-value without also looking at effect size and sample size

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the dataset's generation details, and this task's exact
verification checks -- spoilers. Don't read it before finishing this task.
