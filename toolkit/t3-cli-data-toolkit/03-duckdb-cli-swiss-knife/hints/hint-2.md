# Hint 2 — mechanism

- **Q1**: `read_parquet` takes a glob string directly, and a
  `hive_partitioning=true` named argument to expose the
  `category=<value>` path segments as a real `category` column you can
  `GROUP BY`. Without that flag, the partition value isn't a column at
  all.
- **Q2**: a normal `JOIN ... USING (product_id)` between the
  `read_parquet(...)` expression and a `read_csv(...)` expression works
  exactly like joining two tables — DuckDB doesn't care that neither side
  is a persisted table.
- **Q3**: `LAG(price) OVER (PARTITION BY product_id ORDER BY ts)` gives
  you the previous row's price within each product's own timeline, so
  `price - LAG(price)` is the step-to-step delta. `LAG` returns `NULL` on
  each partition's first row — filter those out before ranking. To keep
  only the single biggest-delta row per product (with the earlier-`ts`
  tie-break), rank rows within each product by `delta DESC, ts ASC` using
  a second window function and keep rank 1 — either via `QUALIFY` or a
  wrapping subquery/CTE.
