No ready-made code here -- just the concrete shape of each of the three
functions.

**`build_pipeline()`**: one `ColumnTransformer` with two named transformers
-- a `OneHotEncoder(handle_unknown="ignore")` over the categorical columns
(`category`, `source_site`), and a `StandardScaler()` over the numeric
columns (`seller_rating`, `discount_pct`, `in_stock`, `day_of_week`) --
plus `remainder="passthrough"` on the `ColumnTransformer` itself. Feed that
into a regressor (`Ridge()` or `HistGradientBoostingRegressor()`, either is
fine) as the second and final step of a `Pipeline`. Return it without
calling `.fit()`. The `remainder="passthrough"` part matters: it's what
lets the same pipeline definition handle an extra numeric column
(`product_mean_logprice`) showing up in the input later, without editing
the `ColumnTransformer`.

**`leaky_holdout_r2(df)`**: filter to valid rows, compute `y =
log(price)`. Group ALL of those rows by `product_id` and take the mean of
`y` within each group -- this is a pandas `groupby(...).transform("mean")`
or equivalent, applied BEFORE you've called `make_split` at all. Attach
that per-row value as a new column, `product_mean_logprice`. Only now call
`make_split(df)`. Slice out the train rows and the test rows (features:
the categorical/numeric columns above, plus `product_mean_logprice`;
target: `y`). `build_pipeline()`, `.fit()` on train, `.predict()` on test,
compute R^2 (`sklearn.metrics.r2_score(y_test, y_pred)` or
`pipeline.score(X_test, y_test)`).

**`correct_holdout_r2(df)`**: same shape, different order. Call
`make_split(df)` FIRST. Filter to valid rows and compute `y = log(price)`.
Group only the TRAIN rows by `product_id`, take the mean of `y` per group
-- this gives you a lookup table (product_id -> average train log-price)
built from train data alone. Map that lookup onto EVERY row (train and
test) to produce `product_mean_logprice`; for a `product_id` not present
in the lookup (never appeared in train), fill in the overall mean of `y`
over the train rows instead. Build features/target for train and test
exactly as before, `build_pipeline()`, fit on train, score on test.

Compare the two R^2 numbers you get back. If they're close, something's
off -- either the leaky version isn't leaking (check the grouping really
does happen on the full, unsplit data) or the correct version accidentally
still includes test information somewhere in its group-by.
