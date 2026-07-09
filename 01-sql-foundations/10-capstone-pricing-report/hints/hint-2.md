# Hint 2

- Root category walk: a `WITH RECURSIVE` CTE seeded from `categories WHERE parent_id
  IS NULL` (carrying its own id and name forward as "root_id"/"root_name"), unioned
  with a recursive step that joins `categories` to the CTE on `child.parent_id =
  cte.id`. The result maps every category id (at any level) to its root id and root
  name. Join `products` to this mapping via `category_id`.
- As-of exchange rate: for a given snapshot's `currency` and `captured_at::date`, you
  want the exchange_rates row with the same currency and the largest `rate_date` that
  is `<=` the snapshot's date. A `LATERAL` subquery per snapshot row, ordered by
  `rate_date DESC LIMIT 1`, does this correctly and efficiently. A plain join on exact
  date equality would silently drop rows whenever a date is missing.
- Month-over-month: `LAG(median_price_usd) OVER (PARTITION BY root_name ORDER BY
  month)` gives you the previous month's median for the same root; the percent-change
  arithmetic and the "guard against NULL/zero" logic wrap around that.
- `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY <expr>)` is the median aggregate —
  it's a different syntax shape from `AVG`/`COUNT`, note the `WITHIN GROUP`.
