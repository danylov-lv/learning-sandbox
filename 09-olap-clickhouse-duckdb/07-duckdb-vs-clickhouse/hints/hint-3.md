Concrete shape for each function, without handing you the SQL string:

- `ch_answer(client)`: run a query against `observations_raw` that selects
  three things in this order -- the `category` column, a `count(*)`-style
  expression, and an `avg(price)`-style expression -- filtered to in-stock
  rows and grouped by category. Use `client.query(sql).result_rows` (or the
  harness `ch_query(sql, client=client)` helper) to get back a list of row
  tuples, one per category. Loop over those tuples and build a dict keyed by
  the first element of each tuple, valued by `(int(second), float(third))`.

- `duck_answer(con)`: same three-expression `SELECT` (category, count,
  avg(price)), but the `FROM` clause is `read_parquet('<glob>',
  hive_partitioning=true)` where `<glob>` is whatever `parquet_glob()`
  returns -- build the SQL string with an f-string so the glob path gets
  interpolated in. Filter and group exactly the same way. Run it with
  `con.execute(sql).fetchall()`, which gives you the same shape of row
  tuples as the ClickHouse side, so the dict-building step is identical
  code.

If `tests/validate.py` tells you the two engines disagree on a count or an
average, the two most likely culprits are: an `in_stock` filter that isn't
actually filtering (check the column's type on each side -- `UInt8` vs
`BOOLEAN` need different-looking, but equivalent, comparisons), or a
`category` set mismatch caused by forgetting `hive_partitioning=true` on the
DuckDB side (without it, `category` isn't a column at all and the query
either errors or silently groups on the wrong thing).
