`RANGE BETWEEN INTERVAL '30 days' PRECEDING AND CURRENT ROW` (paired with
`ORDER BY captured_at` inside the same `OVER (...)`) defines the window as
"every row whose `captured_at` falls within 30 days before this row's
`captured_at`," regardless of how many rows that is. Compare that to `ROWS
BETWEEN 5 PRECEDING AND CURRENT ROW`, which always grabs exactly 6 rows no
matter how far apart in time they are. You'll need both `AVG(...)` and
`STDDEV_SAMP(...)` as window functions over that same frame.
