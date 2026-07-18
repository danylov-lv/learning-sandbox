A concrete walk through each fact, prose only -- translate each of these
into the pandas call and the polars call yourself.

- **`n_obs`**: the row count of the whole table, full stop. pandas:
  length of the DataFrame. polars: height of the DataFrame. No filtering,
  no grouping.

- **`n_products`**: the count of DISTINCT values in the `product_id`
  column -- not the row count. Many rows share a `product_id` (the same
  product gets scraped repeatedly over the 90-day window), so this number
  will be noticeably smaller than `n_obs`. Both libraries have a direct
  "number of unique values in this column" method.

- **`per_category_count`**: group ALL rows by `category` and count them,
  turned into a `{category_name: count}` dict with plain `str` keys and
  plain `int` values. No price filtering here -- a row with a broken price
  still belongs to its category.

- **`valid_price_median` / `valid_price_mean`**: first build the "valid"
  boolean mask exactly as defined in `src/eda.py`'s module docstring
  (price not NaN, price > 0, currency == "USD" -- all three, combined with
  AND). Filter the price column down to only the rows where that mask is
  true, then take the median and the mean of THAT filtered column. Expect
  the median and mean to differ meaningfully -- that's the signature of a
  right-skewed distribution, not a bug.

- **`nan_price_rate`**: the fraction (not the count) of ALL rows where
  `price` is NaN/null. That's a count of missing prices divided by
  `n_obs`. Note this is a DIFFERENT slice than the "valid" mask above --
  NaN is only one of several reasons a row can be invalid, but this fact
  specifically isolates the missingness rate.

- **`per_source_site_count`**: identical pattern to `per_category_count`,
  grouped on `source_site` instead of `category`. No price filtering.

- **`busiest_day`**: truncate `scraped_at` to a calendar date (drop the
  time-of-day component), group ALL rows by that date, count them, and
  take the date with the largest count. Format the winning date as an ISO
  `"YYYY-MM-DD"` string -- both pandas' `datetime.date` and polars'
  `date` objects stringify to exactly that format via `str(...)`.

**The pandas/polars equivalence, concretely**: for every fact above, the
two implementations are answering the identical question over the identical
rows -- they should never legitimately disagree. If your two numbers don't
match, the bug is almost always one of: (a) the "valid" mask built
differently in the two versions (e.g. forgetting the `currency == "USD"`
condition in one), (b) a scalar type mismatch masking a real difference
(comparing a numpy float to a Python float is fine; comparing a dict with
`numpy.int64` values to one with plain `int` values inside a strict
equality check is not, if the validator's dict-equality path expects
plain types), or (c) `summarize_polars()` accidentally re-reading a
different file, or reading the parquet lazily and never actually
`.collect()`-ing before you inspect a value.
