# Hint 3

Rough shape, not code:

**`contracts.py`**

- `id`: int, not null.
- `slug`, `url`, `category`, `brand`: str, not null (no extra rule needed
  beyond "present and typed" — nothing plants a defect in these).
- `title`: str, not null, plus a check that rejects the empty string after
  stripping (a `Check.str_length(min_value=1)` on a column that's already
  `nullable=False` handles both "missing" and "empty" in one place if you
  strip first, or write a custom check — either is fine).
- `currency`: str, not null, `Check.isin(ALLOWED_CURRENCIES)`.
- `in_stock`: bool, not null.
- `seller_id`, `review_count`: int, not null.
- `rating`: float, **nullable=True** — do not add a not-null check here,
  `review_count == 0` legitimately means `rating` is `null` and that is
  correct data, not a defect.
- `price`: numeric dtype with `coerce=True`, `nullable=False`,
  `Check.gt(0)`, plus an upper-bound check. For the upper bound: dump the
  prices you actually see across a sample of live records, sorted — you
  will not find anything close to justifying a flat ceiling below a few
  thousand; pick a round number comfortably above the real maximum you
  observe and don't overthink the exact value, this rule exists to catch a
  clearly-broken number (an extra digit, a unit error), not to be a tight
  bound.
- `description`: str, not null, plus the one custom check you have to
  design after actually looking at a corrupted record — don't guess at the
  signal, go fetch a broken one and read it.
- Set `strict=` after deciding what to do about `_nonce`/`shipping_info` —
  the straightforward path is to drop/flatten them in `gate.py`'s
  normalize step BEFORE validating, so the schema only ever sees the
  columns it was designed for and can safely be strict about anything
  else.

**`gate.py`**

- `run_gate`: build the frame with something like
  `pd.DataFrame(records)` (after stripping `_nonce` and handling
  `shipping_info` however you decided), keep the ORIGINAL records list
  around indexed the same way (so you can look failures back up by
  position), call `schema.validate(df, lazy=True)`, catch
  `SchemaErrors`, and use `err.failure_cases`'s row-index column to figure
  out which original records failed. `df.index` not matching your
  `records` list's order/length after any filtering is the most common
  bug here — validate the FULL frame in one call, don't pre-filter
  anything before validating, or your index bookkeeping breaks. Group
  `failure_cases` by row index, join the `column`/`check` values for that
  index into one string, and that's your `reason` for that row.
- `field_completeness`: a dict comprehension over the union of keys seen
  across all records, each value being `count(present) / len(records)`.
- `completeness_alert`: a list comprehension over `thresholds.items()`,
  comparing `completeness.get(field, 0.0)` against each threshold.
