# Correlation vs Causation -- Backed by Your Own Numbers

Fill in every section using the actual numbers `uv run python tests/
validate.py` prints (and whatever you print yourself while exploring) from
your own `pooled_correlation` and `within_category_correlations` output --
not general statistics folklore, not numbers from someone else's run.

## The naive conclusion

[fill in -- state the pooled correlation you measured between
`discount_pct` and `units_sold`, and the conclusion a PM reading only that
number would draw. What decision would they make based on it?]

## What the within-category analysis shows

[fill in -- report the within-category correlations you measured (name at
least the smallest and largest). Compare them directly against the pooled
number. What happens to the association once you stop pooling across
categories?]

## The confounder

[fill in -- name the variable `identify_confounder` returns, and explain
concretely, in terms of this dataset, why it satisfies both halves of being
a confounder: it plausibly influences `discount_pct` on its own, it
plausibly influences `units_sold` on its own, and conditioning on it is
what made the pooled association mostly disappear.]

## Correlation vs causation

[fill in -- explain, in your own words and referencing your own numbers,
why a strong pooled Pearson correlation does not, by itself, license the
claim "discounting causes higher sales." What is Simpson's paradox, and how
does this dataset demonstrate it?]

## What evidence would support a causal claim

[fill in -- what would actually need to be true, or what experiment would
actually need to be run, before you'd sign off on "discounting drives
sales" as a causal claim? Consider both a randomized approach (what would
you randomize, and at what level -- product? category?) and an
observational approach (what would controlling for confounders in a
regression need to include, and would you still trust it as much as a
randomized experiment).]
