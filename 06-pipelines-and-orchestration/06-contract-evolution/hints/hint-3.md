# Hint 3

Drift detection, concretely: after your lazy `.validate()` fails, you have
`failure_cases` — group it by `(column, check)` and count. Compute what
fraction of the day's total row count each `(column, check)` group accounts
for. If a `(column, check)` group's row count is close to the *entire*
batch size, treat that as structural drift for that column/check rather
than routing those rows to quarantine one by one. Two concrete signatures
you'll see, corresponding to the two drift events:

- A "column not in schema" style failure hitting essentially every row ->
  additive field drift (the `seller_rating` case).
- A dtype/coercion failure on the `price` column hitting essentially every
  row -> type-change drift (the price-as-string case).

For the response: send the alert, write the whole day's rows (or just the
ones implicated in the drift-level failure — your call) to quarantine with
a reason like `"schema_drift: ..."`, and stop — don't fall through to a
partial `core` insert for that day. Once you've evolved the contract and
rerun, the same rows should sail through as normal passing rows, not
quarantine entries.

Locale-price parsing rule (the actual disambiguation): every drift-B price
string is built from a *symbol* prefix (`$`, `€`, `£`) in one style, or a
trailing *3-letter ISO currency code* (`USD`/`EUR`/`GBP`) in the other. That
prefix/suffix marker is unambiguous and always present — check for it
first, and let it decide which separator convention (comma-decimal vs.
dot-decimal) applies to the rest of the string, rather than trying to infer
the convention from the digits and separators alone. Once you know the
style: strip the symbol or currency code and any thousands separators, turn
the decimal separator into `.`, and cast to a Python `Decimal` or `float`
before it reaches your schema. Numeric values (plain JSON numbers, not
strings) should pass through this step untouched — the drift only ever
turns *valid* records' prices into strings; invalid records' `bad_price`
values stay numeric on every day, drift or not.
