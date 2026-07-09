# Hint 2

`captured_at` is a `TIMESTAMP` and `rate_date` is a `DATE`. Comparing them
directly with `=` forces Postgres to compare a timestamp against midnight of
that date — which only matches snapshots captured at exactly 00:00:00.
Casting `captured_at` down to a date fixes the exact-match case, but you
still need the "as-of" idea in your join: for a given snapshot, which
`exchange_rates` row is the right one to use? Think in terms of "the most
recent rate on or before this snapshot's date" rather than "the rate for
exactly this date," even if in practice every date happens to have a row —
building the query to work under the general case is what makes it robust.
