Both functions need: a `WHERE` that keeps only in-stock rows, a `GROUP BY
category`, and two aggregate expressions per group -- a row count and an
average price. That's it; nothing ClickHouse- or DuckDB-specific about the
logic itself. The differences are all mechanical:

- `ch_answer(client)` queries `observations_raw` directly -- it's already a
  table with `category` as a real column. `in_stock` is stored as `UInt8`
  (0/1), not a SQL boolean, in ClickHouse.
- `duck_answer(con)` queries `read_parquet(parquet_glob(), hive_partitioning
  =true)` as a table expression inline in the SQL -- `parquet_glob()` (already
  imported at the top of `src/bench.py`) hands you the glob string, and
  `hive_partitioning=true` is what makes `category` show up as a queryable
  column even though it only exists in the directory names on disk, not
  inside the Parquet files. `in_stock` in the Parquet files is a real
  boolean.

Both hand back row tuples you need to turn into `{category: (count,
avg_price)}` -- look at how the validator/baseline read the result
(`client.query(...).result_rows` for ClickHouse, `con.execute(...).fetchall()`
for DuckDB) and build the dict from whatever tuples come back.
