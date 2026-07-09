# Hint 3

Shape of the approach:

1. For each row of `price_snapshots`, you need exactly one matching
   `exchange_rates` row: the one with the same `currency` and the largest
   `rate_date` that is still `<= captured_at::date`.
2. In PostgreSQL, express "for each outer row, find the best matching inner
   row" with a `JOIN LATERAL (...) ON true`, where the lateral subquery
   filters `exchange_rates` by `currency = <outer>.currency AND rate_date <=
   <outer>.captured_at::date`, orders by `rate_date DESC`, and takes just the
   top row (`LIMIT 1`).
3. Join that lateral result into your main query alongside `sources` (for
   `tier`), then `GROUP BY` month (`date_trunc` on `captured_at`) and `tier`
   to produce `snapshot_count` and the summed/rounded USD amount.
4. Re-run your snapshot-count sanity check from hint 1 against this new
   query — it should now match `price_snapshots` exactly.
