# Hint 2

- The week bucket comes from `date_trunc`, applied directly to `captured_at`, and
  kept as a real timestamp/date in `GROUP BY` and `SELECT` — never formatted to text
  before grouping.
- `distinct_products` needs `COUNT(DISTINCT product_id)`.
- `distinct_product_source_pairs` needs `COUNT(DISTINCT ...)` over a composite —
  Postgres accepts a row expression like `(col_a, col_b)` inside `COUNT(DISTINCT ...)`.
- The USD-only average is a restriction on which rows feed one specific aggregate,
  not a restriction on the whole query — if you put it in a `WHERE` clause you'll
  also drop those rows from `snapshot_count` and the other aggregates, which is wrong.
  There's a clause that lets you filter rows per-aggregate instead.
- You need exactly two grouping keys: the truncated week and the tier. The tier lives
  on `sources`, not on `price_snapshots` — one join.
