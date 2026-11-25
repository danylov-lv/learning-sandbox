"""t03 -- matplotlib fundamentals: a one-glance 2x2 dashboard over the
shared scraped-price dataset.

Implement `build_dashboard(df)` below. It must build ONE matplotlib Figure
containing EXACTLY 4 subplots (a 2x2 grid via `plt.subplots(2, 2, ...)` or
`fig.add_subplot(2, 2, i)` -- either is fine, just end up with exactly 4
Axes on the figure) and return `(fig, facts)`.

Use the Figure/Axes object API (`fig, axes = plt.subplots(...)`, then call
methods on each `ax`), not the pyplot global-state API (`plt.plot(...)`,
`plt.title(...)`), for anything after the figure is created -- with 4
panels sharing one figure, pyplot's "current axes" state makes it too easy
to draw the wrong thing onto the wrong panel. Use the `Agg` backend (or any
non-interactive backend) so this runs headless -- do not call `plt.show()`
anywhere in this file.

Every axis on the figure MUST have a non-empty title (`ax.set_title(...)`),
xlabel (`ax.set_xlabel(...)`), and ylabel (`ax.set_ylabel(...)`). The figure
itself needs a suptitle (`fig.suptitle(...)`). The validator checks all of
this structurally; it cannot judge whether your chosen wording is good --
that part is on you.

The dataset (`df`, as returned by `harness.common.load_observations()`) has
these relevant columns: `price` (float, may be negative/zero/NaN --
parsing defects), `currency` (mostly "USD", ~2% "EUR"/"GBP"), `category`
(one of 8 strings), `scraped_at` (datetime, a fixed 90-day window),
`source_site` (one of 3 strings). "Valid price" for every panel below means:
`currency == "USD"` AND `price > 0` AND `price` is not NaN -- filter this
ONCE and reuse it; don't let currency-mismatched rows or price defects (a
negative price, a zero price, a price with a dropped decimal point, or a
missing/NaN price) leak into any panel.

The 4 required panels, in whatever grid position you like:

1. **Price histogram, log x-scale.** A histogram of valid prices, with the
   x-axis (price) on a LOG scale (`ax.set_xscale("log")`). Price is drawn
   from a log-normal distribution per category -- heavily right-skewed. On
   a linear x-axis nearly every bar collapses into the first few bins and
   the long tail is unreadable; a log x-axis is what makes the shape of
   this distribution visible at all. This is the point of the panel: log
   scales exist for exactly this kind of data.
2. **Boxplot of valid price by category.** One box per category (8 boxes
   total, `df["category"]` has 8 distinct values) showing the valid-price
   distribution within each. Compare spread and median across categories
   at a glance.
3. **Daily median valid price, time series.** One line, x = date (derived
   from `scraped_at`), y = the median of valid `price` for observations
   scraped that day, across the full 90-day window. Look at
   `df["scraped_at"].dt.date` (or `.dt.floor("D")`) plus a `groupby` to get
   one point per day.
4. **Observation counts by source_site, bar chart.** One bar per distinct
   value of `source_site` (3 total), height = number of observations from
   that site. This one is NOT filtered to valid prices -- it's a count of
   every observation, by site.

Return `facts`, a plain dict, alongside the figure:

```python
facts = {
    "n_boxplot_categories": ...,  # int: how many boxes panel 2 has (should be 8)
    "price_axis_is_log": ...,     # bool: True, confirming panel 1's x-axis is log
    "n_days_plotted": ...,        # int: how many distinct days panel 3's line covers
    "n_source_sites": ...,        # int: how many bars panel 4 has (should be 3)
}
```

The validator recomputes each of these independently from the dataset (and,
for `price_axis_is_log`, by inspecting the actual Axes) and compares against
what you report -- `facts` exists so a structural check can confirm the
numbers behind your plot are right, not just that *some* chart was drawn.
"""


def build_dashboard(df):
    """Build the 4-panel (2x2) dashboard figure described in this module's
    docstring above.

    Args:
        df: the full observations DataFrame, as returned by
            `harness.common.load_observations()`. Not pre-filtered --
            filtering to "valid price" rows (USD, price > 0, not NaN) is
            your job, and only for the panels that call for it (see above;
            panel 4 uses every row, unfiltered).

    Returns:
        A tuple `(fig, facts)`:
          - `fig`: a `matplotlib.figure.Figure` with exactly 4 Axes (a 2x2
            grid), every axis carrying a non-empty title/xlabel/ylabel, and
            a non-empty figure suptitle.
          - `facts`: a dict with the four keys documented above
            (`n_boxplot_categories`, `price_axis_is_log`, `n_days_plotted`,
            `n_source_sites`), each independently checkable against the
            dataset.
    """
    raise NotImplementedError
