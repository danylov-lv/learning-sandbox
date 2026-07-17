# Hint 2

`pandera.pandas.DataFrameSchema(columns={...}, strict=..., coerce=...)`.
Each entry in `columns` is a `Column(dtype, checks=[...], nullable=...)`.
A `Check` can be a built-in (`Check.gt(0)`, `Check.isin([...])`,
`Check.str_length(min_value=1)`) or a custom one built from a function over
a pandas Series (`Check(lambda s: ~s.str.contains(...), error="...")`) —
you'll need a custom one for exactly one of the six defects.

`nullable=False` on a `Column` is what actually catches a MISSING value —
if you build your DataFrame from a `list[dict]` where some dicts don't
have a `"price"` key at all, pandas fills that cell with `NaN`
automatically; a non-nullable numeric column then correctly flags it. A
`price` cell holding the literal string `"N/A"` is a different failure
mode: if the column's dtype ends up as `object` (because it has a mix of
floats and one string in it), a numeric `Column(float, coerce=True)` will
fail to coerce that row and pandera will report it as its own kind of
failure — that's fine, it still ends up in `failure_cases`, you don't need
to special-case the string yourself.

`schema.validate(df, lazy=True)` either returns the (possibly coerced)
DataFrame on full success, or raises `pandera.errors.SchemaErrors`. Catch
that exception and look at `err.failure_cases` — it's a DataFrame with one
row per failed check per record. The columns on it tell you which original
row index failed, which column, and which check. Look at it directly
(`print(err.failure_cases)`) before writing any code that processes it —
guessing its shape wastes more time than inspecting it once.

For `strict`: it controls what happens when the DataFrame you hand to
`.validate()` has a column the schema doesn't know about. Think about
`_nonce` and `shipping_info` here — if you don't strip/flatten them before
validating and your schema is strict, what happens? That's the concrete
question `strict=True` vs `strict=False` (or `strict="filter"`) is
answering for you; pick based on what a boundary contract should actually
do with an unexpected field, not by trial and error until something stops
erroring.

For the completeness monitor: it's a plain Python function over
`list[dict]`, no pandera involved. "Non-null/non-empty" is the ENTIRE
definition — don't reach for the pandera schema here, that would conflate
validity with completeness, which is exactly the distinction this function
exists to keep separate.
