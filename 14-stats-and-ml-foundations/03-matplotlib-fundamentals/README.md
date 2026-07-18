# 03 -- Matplotlib Fundamentals

## Backstory

A stakeholder who does not want to open a notebook has asked for "just a
picture" of the scrape you've been running -- something they can glance at
in a standup and get a feel for what the data looks like: are prices
sane, is one category way more expensive than the rest, is anything
trending, are all three source sites actually contributing data. You could
hand them four separate charts across four separate emails, or you could
build one dashboard figure that answers all of it in one look.

This is also, not coincidentally, the last "just plotting" task before Arc
B starts asking you to *defend* numbers with charts -- confidence
intervals, bootstrap distributions, A/B test results. Every one of those
tasks assumes you already know how to open a Figure, put more than one Axes
on it, and label each one so a reader doesn't have to guess what they're
looking at. This task is where that skill gets built, once, properly.

## What's given

- `src/plots.py` -- a single function stub, `build_dashboard(df)`, with a
  rich docstring spelling out exactly what each of the 4 panels must show,
  which dataset columns to use, what "valid price" means for filtering, and
  the `facts` dict you must return alongside the figure. No plotting code is
  provided -- you write all of it.
- The shared dataset, via `harness.common.load_observations()`: one row per
  scrape observation, with `price`, `currency`, `category`, `scraped_at`,
  and `source_site` columns among others (see the module README for the
  full schema). It has NOT been cleaned for you -- `price` has genuine
  parsing defects (negative, zero, a dropped decimal point, missing/NaN)
  and `currency` is occasionally non-USD. Filtering to "valid price" rows
  is part of the task.

## What's required

Implement `build_dashboard(df) -> tuple[matplotlib.figure.Figure, dict]` in
`src/plots.py`. It must return a Figure with **exactly 4 subplots in a 2x2
grid**:

1. **Histogram of valid prices, log x-scale.** Valid = `currency == "USD"`,
   `price > 0`, not NaN. Price is log-normal per category, so it's heavily
   right-skewed -- a linear x-axis is close to unreadable (nearly every
   observation piles into the first couple of bins). Put the x-axis on a
   log scale (`ax.set_xscale("log")`) so the actual shape of the
   distribution becomes visible.
2. **Boxplot of valid price by category.** One box per category -- 8 boxes
   total.
3. **Time series: daily median valid price.** One line, x = date, y = that
   day's median valid price, across the full 90-day scrape window.
4. **Bar chart: observation counts by source_site.** One bar per source
   site (3 total), height = number of observations -- unfiltered, every
   row counts here, not just valid-price ones.

Every one of the 4 Axes needs a non-empty `title`, `xlabel`, and `ylabel`.
The Figure needs a non-empty `suptitle`. Use the Figure/Axes object API
(`fig, axes = plt.subplots(2, 2, ...)`, then methods on each `ax`) rather
than pyplot's global "current axes" state -- with 4 panels on one figure
it's too easy for pyplot-style calls to land on the wrong one.

Alongside the figure, return a `facts` dict:

```python
{
    "n_boxplot_categories": <int>,   # boxes in panel 2, should be 8
    "price_axis_is_log":    <bool>,  # True, confirming panel 1's x-axis is log
    "n_days_plotted":       <int>,   # distinct days panel 3's line covers
    "n_source_sites":       <int>,   # bars in panel 4, should be 3
}
```

This exists because visual correctness isn't something a script can judge --
the validator ties your plot to real numbers it can check independently
instead.

## Completion criteria

```bash
cd 14-stats-and-ml-foundations
uv run python 03-matplotlib-fundamentals/tests/validate.py
```

The validator checks structure only: a Figure with exactly 4 Axes, each
carrying a non-empty title/xlabel/ylabel, a non-empty suptitle, and a
`facts` dict whose values match independently recomputed references (the
real category count, the real source-site count, the real day count, and
whether any Axes actually has a log x-scale). It prints `PASSED` with a
short summary, or `NOT PASSED: <reason>` and exits 1.

**What it cannot check, and what is on you to get right by eye:** whether
the histogram is actually readable, whether the boxplot's category order
makes sense, whether the time-series line looks like a real time series
and not a scatter of noise, whether the bar chart's bars are in a sensible
order, whether your label text is clear rather than just non-empty. Open
the figure (`fig.savefig(...)` and view the PNG, or run interactively and
call `plt.show()` outside of `plots.py`) and actually look at it before
calling this done.

## Estimated evenings

1

## Topics to read up on

- The matplotlib Figure/Axes object API vs. the pyplot state-machine API,
  and why the former scales better to multi-panel figures
- `plt.subplots(nrows, ncols)` and the grid of Axes it returns
- Log-scaled axes: when and why (`ax.set_xscale("log")`), and how a
  log-normal / right-skewed distribution looks different under it
- Boxplots: what the box, whiskers, and outlier points each represent
- Grouping a datetime column by calendar day (`.dt.date` /
  `.dt.floor("D")`) and plotting the result as a line
- Labeling discipline: titles, axis labels, and a figure-level suptitle as
  the minimum bar for a chart someone else has to read without you in the
  room

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the dataset's generation details, and this task's exact verification
checks -- spoilers. Don't read it before finishing this task.
