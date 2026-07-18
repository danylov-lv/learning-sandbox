Concrete sequence, no ready code:

1. `pooled_correlation`: pick one correlation function (`pandas.Series.corr`,
   `numpy.corrcoef`, or `scipy.stats.pearsonr` all work) and apply it to
   `df["discount_pct"]` and `df["units_sold"]` directly, no grouping. You
   should land somewhere around 0.8 -- if you get something close to zero
   or a NaN, check you're not accidentally correlating a column against
   itself or passing something that isn't numeric.

2. `within_category_correlations`: `df.groupby("category")`, and for each
   group apply the exact same correlation call to that group's
   `discount_pct` and `units_sold`. Build a `{category: r}` dict from the
   result -- don't hardcode the list of category names, read them off the
   grouped data so this doesn't silently break if the dataset changes. You
   should see every value land far closer to zero than the pooled number.

3. `identify_confounder`: this is a one-line return once steps 1 and 2 are
   done and you've looked at the gap between them -- the answer is a single
   column name from `df.columns`, chosen because conditioning on it (step
   2) is what made the association from step 1 mostly vanish.

4. `make_figure`: `ax.scatter(df["discount_pct"], df["units_sold"], c=...)`
   with points colored by category (map each category name to a color, or
   pass an integer code derived from category and a `cmap`), a legend, plus
   two kinds of trend line: one fit and drawn per category (using only that
   category's rows), and one fit and drawn on the pooled data across all
   categories. `numpy.polyfit(x, y, 1)` gives you the slope/intercept of a
   least-squares line for any x/y pair; draw it with `ax.plot` over a
   sorted or evenly spaced x range.

5. `ANSWER.md`: the numeric case is done by step 3. The write-up sections
   ask you to explain WHY this pattern is called Simpson's paradox, name
   category concretely as the confounder with reference to the actual
   `CATEGORY_BASE_DISCOUNT`/`CATEGORY_BASE_UNITS`-style intuition (some
   categories are just discounted more AND sell more, independent of any
   real per-category discount effect), and describe what a randomized
   experiment (randomizing discount depth within a category, not across
   categories) or a proper regression adjustment would need to look like
   before "discounting causes sales" would be a defensible claim.
