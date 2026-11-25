"""t09 -- correlation vs causation: is category confounding the discount/
units-sold correlation?

The shared dataset (`df`, as returned by `harness.common.load_observations()`)
has, among others, three relevant columns: `discount_pct` (float, 0-0.6),
`units_sold` (int, Poisson-distributed), and `category` (one of 8 strings).
Computed over the WHOLE dataset, `discount_pct` and `units_sold` are
strongly correlated -- a dashboard built on this data would show a Pearson
r around 0.8. It is tempting to read that as "discounting drives sales" and
recommend discounting harder everywhere.

Your job is to check whether that pooled correlation survives conditioning
on `category`, using nothing but Pearson correlation computed two different
ways (once over the whole dataset, once separately inside each category),
compared side by side.

Implement the four functions below. No solution is provided anywhere in
this task -- work it out from the docstrings, the README, and the hints.
"""


def pooled_correlation(df):
    """Pearson correlation coefficient between `discount_pct` and
    `units_sold`, computed over the ENTIRE dataset -- no grouping, no
    filtering by category.

    This is the number a naive dashboard would show: "discount and sales
    move together at r = ~0.8." It is real -- the two columns really are
    that correlated across the pooled data -- but a strong pooled
    correlation says nothing on its own about whether one variable is
    driving the other. That question is what the rest of this module's
    functions exist to interrogate.

    Args:
        df: the full observations DataFrame, as returned by
            `harness.common.load_observations()`. Not pre-filtered --
            use `discount_pct` and `units_sold` directly.

    Returns:
        A single float: the Pearson correlation coefficient between
        `df["discount_pct"]` and `df["units_sold"]`. Use whichever
        correlation implementation you like (`pandas.Series.corr`,
        `numpy.corrcoef`, `scipy.stats.pearsonr`) -- they should all agree
        to many decimal places on the same data.
    """
    raise NotImplementedError


def within_category_correlations(df):
    """Pearson correlation coefficient between `discount_pct` and
    `units_sold`, computed SEPARATELY within each distinct value of
    `category` -- i.e. the same statistic as `pooled_correlation`, but
    conditioned on (stratified by) category instead of pooled across it.

    This is the stratification step: if the strong pooled correlation is
    actually explained by category (some categories both discount more AND
    sell more units at baseline, with little relationship between the two
    inside any single category), then computing the correlation separately
    inside each category should make most of it disappear. If the
    relationship were genuinely causal -- discounting itself drives units
    sold, independent of category -- you would expect the within-category
    correlations to stay close to the pooled value, not collapse toward
    zero.

    Args:
        df: the full observations DataFrame, as returned by
            `harness.common.load_observations()`.

    Returns:
        A dict mapping each distinct `category` value present in `df` to
        the Pearson correlation coefficient between `discount_pct` and
        `units_sold` computed on the subset of rows belonging to that
        category. One entry per distinct category (8 in the shipped
        dataset) -- don't hardcode the category list, derive it from `df`.
    """
    raise NotImplementedError


def identify_confounder(df):
    """Name the column in `df` that is confounding the pooled
    `discount_pct` / `units_sold` correlation.

    Don't guess this from reading the module's docstrings or the README --
    arrive at it from your own analysis: a confounder here is a variable
    that (a) plausibly influences both `discount_pct` and `units_sold`
    independently, and (b) when you condition on it (as
    `within_category_correlations` does), the strong pooled association
    mostly disappears. Compare `pooled_correlation(df)` against the values
    in `within_category_correlations(df)` and ask which variable you
    stratified by to make that happen.

    Args:
        df: the full observations DataFrame, as returned by
            `harness.common.load_observations()`.

    Returns:
        The exact column name (a string) of the confounding variable, as
        it appears in `df.columns`.
    """
    raise NotImplementedError


def make_figure(df):
    """Build a matplotlib Figure that makes the confound visible at a
    glance: the classic Simpson's-paradox picture.

    At minimum: a scatter of `discount_pct` (x) vs `units_sold` (y), with
    points colored by `category` so the reader can see which category each
    point belongs to. Beyond the bare scatter, the plot should make the
    reversal/attenuation visible rather than just plausible -- the
    strongest way to do that is to also draw:

      - one trend line (e.g. a least-squares fit, `numpy.polyfit` or
        equivalent) per category, fit only on that category's points, and
      - one trend line fit on the POOLED data (all categories together),
        for contrast.

    Overlaying the per-category trend lines (each close to flat) against
    the pooled trend line (steep) is what turns "category confounds this"
    from an assertion into something the reader can see: the pooled line's
    slope comes almost entirely from where each category's cluster of
    points sits, not from any real within-category relationship.

    Use a non-interactive backend (e.g. `matplotlib.use("Agg")`, or just
    avoid `plt.show()`) so this runs headless. Give the axis a title,
    xlabel, and ylabel and a legend identifying the categories -- the
    validator's structural check only confirms a figure with real drawn
    content exists; making the plot actually communicate the finding is on
    you.

    Args:
        df: the full observations DataFrame, as returned by
            `harness.common.load_observations()`.

    Returns:
        A `matplotlib.figure.Figure` with at least one Axes containing
        real drawn content (scatter points and/or line artists).
    """
    raise NotImplementedError
