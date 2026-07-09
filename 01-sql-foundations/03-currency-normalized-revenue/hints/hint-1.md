# Hint 1

Run a plain equi-join between `price_snapshots` and `exchange_rates` on
currency and date, and count the result. Compare that count against
`SELECT COUNT(*) FROM price_snapshots`. The gap tells you the join condition
you picked isn't matching rows the way you think it is — look closely at the
actual column types involved before changing anything else.
