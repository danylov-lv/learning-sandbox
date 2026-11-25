"""Task 05 -- outliers vs. parsing errors.

The shared dataset's `price` column mixes two very different kinds of
"weird" values, and treating them the same is the mistake this task exists
to prevent:

- **Parsing errors** (a.k.a. defects): the scrape or the ingestion pipeline
  mangled a real price. Four kinds live in this column (see the README for
  the full backstory):
    - negative price (`price < 0`)
    - zero price (`price == 0`)
    - missing-decimal price (`price` is ~100x a plausible price -- a
      dropped decimal point, e.g. "$19.99" scraped/parsed as "1999")
    - NaN price (missing/unparseable)
  These are garbage. They must be quarantined, not averaged into anything.
- **Genuine outliers**: real, unusually expensive products. The price is
  large but it is NOT an artifact -- it's the true, if rare, upper tail of
  that category's price distribution. These must be KEPT. Deleting them
  (e.g. via a naive "drop anything more than 3 std devs from the mean"
  rule) silently deletes your best-margin products from every downstream
  aggregate.

Currency is a separate data-quality axis (rows with `currency != "USD"`)
and is OUT OF SCOPE for this task -- don't fold non-USD rows into either
bucket below; leave them wherever the rest of your logic would otherwise
put them based on `price` alone. "Parsing error," in this task, means a
`price`-column defect only.

Implement the two functions below.
"""

import pandas as pd


def classify_prices(df: pd.DataFrame) -> dict:
    """Classify every row's `price` as a parsing error or a usable value
    (usable INCLUDES genuine outliers -- a large-but-real price is not an
    error).

    The naive approach -- flag anything more than N standard deviations
    from the mean price -- fails here, and you can prove it to yourself:
    the missing-decimal defects are themselves so large they blow up the
    mean and standard deviation, and whatever threshold you land on either
    misses most of the missing-decimal rows, or catches them along with the
    genuine outliers you were supposed to keep. A method built on the mean
    and standard deviation of a column that isn't remotely normal is the
    wrong tool -- see the README's "Topics" list.

    A reliable method separates the two failure modes with a different
    check for each, roughly:

    1. **Impossible values are free.** A price that is `<= 0` or `NaN`
       cannot be a real price, genuine outlier or not. No further
       reasoning needed -- these are always parsing errors.
    2. **Missing-decimal has a signature, not just a magnitude.** A
       missing-decimal price is `~100x` some perfectly ordinary price for
       that product's category. That means the RAW value can be
       arbitrarily large (nothing stops an ordinary $40 kitchen item from
       becoming a $4000 kitchen "price"), so magnitude alone can't be the
       test. What CAN be tested: does the value become plausible again once
       you divide it by 100? "Plausible" should be judged against a
       *robust* per-category notion of "typical" -- something like the
       median (or a log-scale median) of that category's usable prices,
       not the mean, and not the raw standard deviation (both are exactly
       the statistics a handful of extreme values distort the most).
       Category matters here: a $4000 candidate is ordinary for
       electronics and wildly implausible for books. Also look at the
       value itself, not just its ratio to the category median: a real
       price almost always carries cents; a suspiciously round, whole-
       dollar amount sitting far above where this category's prices
       normally land is exactly what you'd expect a shifted decimal point
       to look like.
    3. **Everything else large is a genuine outlier, not an error.** A
       price that is neither impossible nor carries the missing-decimal
       signature is kept, no matter how large -- that's the whole point of
       this task. A price column WILL have real skew and a real upper
       tail; your job is to not confuse that tail with the defects sitting
       inside it.

    Look at what a flagged row's category/other columns look like before
    committing to a rule -- eyeballing a sample of your flagged (and
    NOT-flagged) rows is the fastest way to catch a rule that's too
    aggressive or too lax.

    Args:
        df: the full observations DataFrame from `harness.common.
            load_observations()` -- one row per scrape observation, with
            (among other columns) `obs_id`, `category`, `price`.

    Returns:
        A dict with exactly two keys:
          - "parsing_error_ids": a set (or sorted list) of `obs_id` values
            for rows whose `price` you're quarantining as a parsing error.
          - "kept_ids": a set (or sorted list) of `obs_id` values for every
            OTHER row -- i.e. every row not in `parsing_error_ids`,
            including genuine outliers. Together the two sets must
            partition every `obs_id` in `df` exactly once (no row missing,
            no row counted in both).
    """
    raise NotImplementedError


def make_figure(df: pd.DataFrame):
    """Build a matplotlib Figure that visualizes the price distribution
    with parsing-errors and kept values visibly distinguished, so the
    separation your `classify_prices` makes is visible, not just asserted.

    You get to choose the exact chart, but it needs to actually show the
    separation -- a couple of approaches that work well for a heavily
    skewed, defect-contaminated price column:

    - A log-scale histogram of `price` (dropping non-positive/NaN values
      before taking the log, or plotting them as a separate marker/bar
      since `log` of a non-positive number is undefined) with kept and
      flagged values in different colors/overlaid.
    - A scatter/strip plot of `price` (log-scale y-axis) by `category`,
      colored by whether each row ended up in `parsing_error_ids` or
      `kept_ids`.

    Either way: call `classify_prices(df)` yourself inside this function
    (or reuse a result you already have) to get the flag for each row --
    don't hardcode a threshold here that's different from what
    `classify_prices` actually used.

    Args:
        df: same DataFrame as `classify_prices`.

    Returns:
        A `matplotlib.figure.Figure` with at least one Axes that has
        actually drawn content (checked structurally by
        `harness.common.require_figure` -- it can't judge whether your
        chart is well-labeled or the right chart type, only that something
        real got drawn).
    """
    raise NotImplementedError
