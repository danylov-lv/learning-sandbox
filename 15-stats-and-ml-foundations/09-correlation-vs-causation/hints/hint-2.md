The mechanical test for "is this correlation confounded by variable X" is
stratification: split the data into groups by X, and recompute the same
correlation separately inside each group.

- If the correlation stays roughly as strong inside every group as it was
  pooled, X isn't explaining it -- whatever relationship the pooled number
  reflects survives conditioning on X, which is at least consistent with
  (though still not proof of) a real relationship between the original two
  variables.
- If the correlation collapses toward zero inside every group, the pooled
  correlation was mostly an artifact of X: the groups differ enough from
  each other on both variables that comparing across groups produces an
  association that isn't there within any single group.

Group `df` by `category` with `pandas.DataFrame.groupby`, and for each
group compute the same Pearson correlation between `discount_pct` and
`units_sold` you computed pooled. Compare the shape of the result (one
number per category) against the single pooled number. `identify_confounder`
should fall out of that comparison directly -- whichever variable you
stratified by to make the association collapse is your answer.
