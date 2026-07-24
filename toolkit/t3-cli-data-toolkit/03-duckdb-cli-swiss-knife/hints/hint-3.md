# Hint 3 — concrete approach

- **Q1**: one `SELECT category, COUNT(*), AVG(price) FROM
  read_parquet('.../parquet/**/*.parquet', hive_partitioning=true) GROUP
  BY category`, aliasing the two aggregates to exactly `obs_count` and
  `avg_price` (the validator checks those field names).
- **Q2**: join the same `read_parquet(...)` expression to
  `read_csv('.../products.csv')` on `product_id`, then
  `GROUP BY region` with the same two aggregates, aliased `obs_count` /
  `avg_price` again.
- **Q3**: build this in two logical stages even if you write it as one
  query — first a `delta` column via `LAG(...) OVER (...)`, then a
  `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY delta DESC, ts
  ASC)` (or `RANK()`) to pick exactly one row per product, filtered to
  `= 1`. `QUALIFY row_number() OVER (...) = 1` after computing `delta` in
  a CTE avoids needing an extra wrapping subquery. Alias the two output
  columns `jump_ts` and `jump_amount`.
- Every call needs `duckdb -json -c "<your SQL>"` so the output is a JSON
  array your `===Qn===` block can be diffed against directly.
