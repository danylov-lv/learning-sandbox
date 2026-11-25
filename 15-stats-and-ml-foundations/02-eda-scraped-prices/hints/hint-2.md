Most of these facts fall into one of two patterns: a straight count/groupby
over ALL rows, or an aggregate computed over a FILTERED subset. Don't mix
the two up -- `per_category_count` wants every row (a category with lots of
broken prices should still show its true row count); `valid_price_median`
wants only the rows that pass the "valid" filter defined in `src/eda.py`'s
module docstring.

Build the valid-row boolean mask FIRST, as its own step, before computing
anything that depends on it. In pandas that's three chained conditions
combined with `&` (not `and` -- pandas needs the vectorized operator) over
`df["price"]` and `df["currency"]`; in polars it's the same three
conditions as `pl.col(...)` expressions combined with `&`, passed to
`.filter(...)`. Getting the mask right once and reusing it for both the
median and the mean is safer than writing two separate filter expressions
that might quietly drift apart.

`value_counts()` in pandas and `.group_by(...).len()` in polars are doing
the same conceptual job for the categorical counts (`per_category_count`,
`per_source_site_count`) -- one groups-and-counts, the other's result needs
turning into a plain dict afterward. Watch the value types you put in that
dict: the validator compares dicts for equality, and a numpy `int64` or a
polars scalar type sitting where a plain `int` is expected can still THINK
it's checking a number correctly against `check_close`, but for a dict
comparison keys and shape matter more than exact type -- cast counts to
`int()` and keys to `str()` explicitly rather than assuming the library's
native scalar behaves the same on both sides.

For `busiest_day`, you need to bucket a timestamp column down to a calendar
date before grouping. pandas: `.dt.date` on the datetime column. polars:
`.dt.date()` as an expression. Both give you something you can group and
count the same way as the categorical facts above; the difference is what
you do with the result once you have the top count (format it as an ISO
`"YYYY-MM-DD"` string either way).
