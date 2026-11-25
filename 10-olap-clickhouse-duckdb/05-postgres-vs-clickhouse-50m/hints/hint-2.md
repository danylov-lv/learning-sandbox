The two tables don't represent "in stock" the same way. In Postgres,
`price_history.observations.in_stock` is a real `BOOLEAN` column -- filter
on it as a boolean. In ClickHouse, `observations_raw.in_stock` is declared
`UInt8` (0 or 1), not a boolean type at all -- filter on it as an integer
comparison, not a boolean literal.

Whichever client library you're using, check what shape it hands back for
each column of a row: `cur.fetchall()` on the psycopg side and
`result.result_rows` on the clickhouse-connect side both give you tuples,
but the Python types inside those tuples (e.g. what a `NUMERIC` average
comes back as vs a `Float64` average) are worth printing once and looking
at directly, rather than assuming.
