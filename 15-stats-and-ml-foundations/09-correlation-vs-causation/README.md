# 09 -- Correlation vs Causation

## Backstory

Someone on the growth team built a dashboard over the scraped product-price
data. One tile jumps out: `discount_pct` and `units_sold` move together
with a Pearson correlation of about 0.8 -- about as strong as real-world
messy data ever gets. The PM reading the dashboard draws the obvious
conclusion: "discounting drives sales -- let's slash prices across the
board and watch volume go up." A rollout plan is already being drafted.

Before you sign off on that plan, you have one job: check whether that
correlation survives being conditioned on the other things that differ
between products. In particular, categories differ wildly in both how much
they get discounted and how many units they naturally move -- toys and
apparel get discounted hard and sell fast; electronics barely gets
discounted and moves slower per listing. If category alone can produce a
strong pooled correlation even when discounting barely matters *within* any
single category, the PM's rollout plan is chasing a statistical artifact,
not a lever that actually works.

## What's given

- `src/confounding.py` -- the scaffold you implement. Four functions, each
  with a rich docstring spelling out its exact contract: `pooled_correlation`,
  `within_category_correlations`, `identify_confounder`, `make_figure`. No
  solution code anywhere.
- The shared dataset, via `harness.common.load_observations()`: every
  observation has `discount_pct` (float, 0-0.6), `units_sold` (int), and
  `category` (one of 8 strings), among other columns you don't need for
  this task.
- `ANSWER.md` -- an unfilled writeup template: five sections asking you to
  walk through the naive conclusion, what stratifying by category actually
  shows, which variable is the confounder, why correlation doesn't license
  the causal claim, and what evidence would.

## What's required

1. Implement all four functions in `src/confounding.py`:
   - `pooled_correlation(df)` -- the Pearson r everyone sees on the
     dashboard: `discount_pct` vs `units_sold`, computed over the whole
     dataset.
   - `within_category_correlations(df)` -- the same statistic, recomputed
     separately inside each category.
   - `identify_confounder(df)` -- the column name of the variable that,
     once you condition on it, makes the pooled association mostly
     disappear. Arrive at this from comparing the two functions above --
     don't just guess the answer and hardcode it.
   - `make_figure(df)` -- a scatter of `discount_pct` vs `units_sold`
     colored by category, with per-category trend lines shown against the
     pooled trend line, so the reversal/attenuation is visible at a
     glance -- the classic Simpson's-paradox picture.
2. Fill in every section of `ANSWER.md`, grounded in the numbers your own
   functions produce -- not general statistics folklore.

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate.py
```

`tests/validate.py`:

- Recomputes `pooled_correlation` and `within_category_correlations`
  independently, straight from `load_observations()`, and checks your
  functions' outputs match within a small tolerance.
- Checks every within-category correlation stays small and clearly, sharply
  below the pooled correlation -- the numeric signature of a confound
  collapsing under stratification.
- Checks `identify_confounder(df) == "category"`.
- Checks `make_figure(df)` returns a real matplotlib Figure with drawn
  content (`require_figure`) -- it cannot judge whether the plot is
  well-labeled or actually communicates the finding; that part is on you.
- Checks `ANSWER.md` has all five required sections, each filled with real
  content past the shipped `[fill in` placeholder, and references enough of
  the module's vocabulary (confounder, category, spurious, Simpson,
  causation, within-category) to show your answer is grounded in what you
  actually computed.
- Prints `PASSED` with the pooled r and the largest within-category |r|, or
  `NOT PASSED: <reason>` and exits 1 -- including when `confounding.py` is
  still unimplemented (`NotImplementedError` surfaces as a clean message,
  no traceback).

## Estimated evenings

1-2

## Topics to read up on

- Pearson correlation coefficient -- what it measures and, just as
  importantly, what it doesn't (direction of causation, whether a third
  variable explains both sides)
- Confounding variables -- a variable that influences both the "cause" and
  the "effect" you're studying, producing an association between them that
  isn't due to either one driving the other
- Simpson's paradox -- how a trend present in pooled data can vanish, or
  even reverse, once the data is split into subgroups
- Stratification / conditioning on a variable -- recomputing a statistic
  separately within subgroups instead of over the pooled data
- What would actually license a causal claim here: a randomized experiment
  (randomly assign discount levels within a category and measure the
  effect) versus observational adjustment (controlling for known
  confounders in a regression) -- and why neither is the same thing as "the
  correlation is strong"

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the exact confound construction, and this task's committed reference
values -- spoilers. Don't read it before finishing this task.
