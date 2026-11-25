"""s14.t02 -- exploratory data analysis over the scraped-price dataset,
computed twice: once in pandas, once in polars, and confirmed to agree.

You inherited a fresh scrape dump. Before anyone downstream trusts a number
you report about it -- a median price, a category breakdown, a missingness
rate -- you need to know your data: how many rows, how many distinct
products, how it's split across categories and source sites, how often the
price field is simply missing, and which day the scraper was busiest.
"Trust but verify" starts here, and one good way to verify your own pandas
answer is to recompute it in a second, independent engine and check the two
agree. That's the polars-vs-pandas taste this task is about: two different
codebases, two different execution models (pandas eager on an in-memory
DataFrame; polars here also eager, but built around a columnar expression
API that scales to lazy/streaming execution you'll meet in later modules),
same question, same answer.

-------------------------------------------------------------------------
The "valid price" definition (READ THIS BEFORE WRITING ANY AGGREGATE)
-------------------------------------------------------------------------
Several facts below are computed "over valid rows only." For THIS task,
a row's price is VALID iff all three hold:

    1. price is not NaN
    2. price > 0
    3. currency == "USD"

This is a deliberately simple, purely-mechanical filter -- exactly the kind
of first-pass data-quality gate you'd write before you've done any deeper
statistical investigation. It catches the obviously-broken rows (missing
price, non-positive price, un-normalized currency) but it will NOT catch
every kind of bad price: a scrape that dropped a decimal point (e.g. "$19.99"
recorded as "1999") still produces a positive, non-NaN, USD price -- it's
just wrong by a factor of ~100. Telling that kind of defect apart from a
genuinely expensive product is a harder statistical problem, and it's the
subject of a later task in this module. Here, use the mechanical definition
above, exactly as stated -- don't try to out-think it.

-------------------------------------------------------------------------
Required dict shape (both summarize_pandas and summarize_polars return
EXACTLY this shape -- same keys, same meaning, values that agree with
each other within float tolerance):
-------------------------------------------------------------------------

    {
        "n_obs": int,                      # total row count, no filtering
        "n_products": int,                 # count of DISTINCT product_id values
        "per_category_count": dict,        # {category: row count}, ALL rows (no price filtering)
        "valid_price_median": float,       # median of price over VALID rows (see definition above)
        "valid_price_mean": float,         # mean of price over VALID rows
        "nan_price_rate": float,           # (# rows where price is NaN) / n_obs
        "per_source_site_count": dict,     # {source_site: row count}, ALL rows
        "busiest_day": str,                # ISO "YYYY-MM-DD" calendar date with the most
                                            # observations by scraped_at date (ties broken by
                                            # whichever date your aggregation returns first --
                                            # the dataset does not produce a tie at the top)
    }

`per_category_count` and `per_source_site_count` must have plain Python
str keys and int values (not numpy/polars scalar types) so the validator's
dict-equality check works cleanly.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.common import OBSERVATIONS_PATH  # noqa: E402


def summarize_pandas(df):
    """Compute the EDA fact dict (see module docstring) using pandas.

    Args:
        df: pandas.DataFrame with the observations schema (obs_id,
            product_id, category, title, price, currency, scraped_at,
            in_stock, seller_rating, source_site, discount_pct, units_sold)
            -- e.g. the return value of `harness.common.load_observations()`.

    Returns:
        dict matching the shape documented in the module docstring.

    Approach sketch (fill in with real pandas calls):
        - `n_obs`: `len(df)`.
        - `n_products`: `df["product_id"].nunique()`.
        - `per_category_count`: `df["category"].value_counts()` gives you
          the counts; turn it into a plain `{str: int}` dict.
        - Build the "valid" boolean mask per the definition above, then
          slice `df.loc[mask, "price"]` and take `.median()` / `.mean()` on
          that slice for `valid_price_median` / `valid_price_mean`.
        - `nan_price_rate`: fraction of rows where `price` is NaN --
          `.isna()` plus a mean, or a count divided by `n_obs`.
        - `per_source_site_count`: same pattern as `per_category_count`,
          grouped on `source_site` instead.
        - `busiest_day`: `scraped_at` is a datetime column; extract the
          calendar date (`.dt.date`), count observations per date, take the
          date with the largest count, and format it as an ISO string
          (`str(...)` on a `datetime.date` already gives `"YYYY-MM-DD"`).
    """
    raise NotImplementedError


def summarize_polars():
    """Compute the SAME EDA fact dict as `summarize_pandas`, independently,
    using polars -- reading `harness.common.OBSERVATIONS_PATH` directly
    with `pl.read_parquet` rather than accepting a pre-loaded DataFrame.

    Returns:
        dict matching the shape documented in the module docstring, with
        values that agree with `summarize_pandas(load_observations())`
        within float tolerance.

    Approach sketch (fill in with real polars calls):
        - `import polars as pl`, then `df = pl.read_parquet(OBSERVATIONS_PATH)`.
        - `n_obs`: `df.height` (or `len(df)`).
        - `n_products`: `df["product_id"].n_unique()`.
        - `per_category_count`: `df.group_by("category").len()` gives you
          a small DataFrame of (category, count) -- convert it to a plain
          `{str: int}` dict (watch out for numpy/polars scalar types
          leaking into the dict values; cast to `int`).
        - Build the "valid" boolean expression per the definition above
          (`pl.col("price").is_not_null() & (pl.col("price") > 0) &
          (pl.col("currency") == "USD")`), `.filter(...)` on it, then take
          `.median()` / `.mean()` of the `price` column on the filtered
          frame for `valid_price_median` / `valid_price_mean`.
        - `nan_price_rate`: fraction of rows where `price` is null.
        - `per_source_site_count`: same group-by pattern as
          `per_category_count`, grouped on `source_site`.
        - `busiest_day`: extract the calendar date from `scraped_at`
          (`pl.col("scraped_at").dt.date()`), group by it, count, find the
          date with the largest count, and format it as an ISO string.
    """
    raise NotImplementedError


def make_figure(df):
    """Build ONE informative EDA figure over `df` and return the Figure.

    Args:
        df: pandas.DataFrame with the observations schema (e.g. the return
            value of `harness.common.load_observations()`).

    Returns:
        matplotlib.figure.Figure with at least one Axes containing actually
        drawn content (a bar chart, a histogram, ...) -- not a blank canvas.

    Pick ONE finding from your summary and make a chart that shows it. Two
    reasonable choices (pick either, or something else that's genuinely
    informative -- this is not graded on chart type):

        - A bar chart of `per_category_count` -- one bar per category,
          height = row count. Immediately shows the category imbalance
          (electronics dominates; garden/books are a small tail).
        - A histogram of valid prices (per the "valid" definition above).
          Price is log-normal-shaped per category, so consider whether a
          linear or a log-scaled x-axis (or plotting `log(price)` directly)
          makes the shape easier to read.

    Remember matplotlib needs the Agg backend in a headless/validator
    context: `import matplotlib; matplotlib.use("Agg")` BEFORE
    `import matplotlib.pyplot as plt` -- do this inside this function (or
    at module import time) so it works regardless of how the validator
    imports this module. Build the figure with `fig, ax = plt.subplots()`,
    draw into `ax`, and `return fig` -- don't call `plt.show()`.
    """
    raise NotImplementedError
