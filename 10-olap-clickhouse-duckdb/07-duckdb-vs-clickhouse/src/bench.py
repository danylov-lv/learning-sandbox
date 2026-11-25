"""s09.t07 -- the SAME analytical query, server vs zero-server.

You've now run this exact aggregate twice already in this module: once
against ClickHouse's `observations_raw` (a MergeTree, running as a server
process on port 8309), once against the Parquet lake via DuckDB (task 06,
no server -- an in-process engine reading files off disk). This task puts
both engines side by side on purpose. Both read the SAME underlying data
(`.authoring/design.md` calls this out explicitly: `observations_raw` and
`data/parquet/category=*/part-0.parquet` are coherent copies of one corpus),
so any difference in the answer is a bug, and any difference in wall-clock
time is the actual subject of this task.

Implement two functions below, each computing:

    per-category (count, avg(price)) over in_stock rows

from a different engine, in the SAME shape so the validator can hold both to
the same answer key and compare them to each other:

    { category: (count, avg_price) }

  * key    -- the category string (one of the 8 in ground truth)
  * count  -- Python int
  * avg    -- Python float

Compute the aggregate IN THE ENGINE (SQL GROUP BY / avg), never by pulling
raw rows into Python and averaging them yourself -- that would make the
timing comparison meaningless (you'd be timing Python, not the engine).

Try both by hand before trusting the validator:

    uv run python baseline.py
    uv run python tests/validate.py
"""

from harness.common import parquet_glob


def ch_answer(client) -> dict:
    """Per-category (count, avg_price) over in-stock rows, computed by
    CLICKHOUSE against `price_history.observations_raw`.

    `client` is a live clickhouse-connect client on the `price_history`
    database (given -- opened via harness `ch_client()`). This is the same
    table and the same aggregate you already wrote in task 01's
    `category_instock_agg()`, if you did that task: filter to `in_stock = 1`
    (a `UInt8`, not a SQL boolean, in ClickHouse), `GROUP BY category`,
    select `category, count(*), avg(price)`.

    Run the query with `client.query(...)` and read `result.result_rows` (a
    list of row tuples), or use the harness `ch_query(sql, client=client)`
    helper. Build the returned dict from those rows: `{category: (count,
    avg_price)}`, count as `int`, avg_price as `float`.

    ClickHouse here is a running SERVER: a long-lived process holding the
    MergeTree parts, ready to answer this query (and any concurrent one)
    without any per-query startup cost beyond the query itself.
    """
    raise NotImplementedError


def duck_answer(con) -> dict:
    """Per-category (count, avg_price) over in-stock rows, computed by
    DUCKDB directly against the Parquet lake -- no server involved.

    `con` is a live in-memory DuckDB connection (given -- opened via harness
    `duckdb_connect()`). Query `read_parquet(parquet_glob(),
    hive_partitioning=true)` -- `parquet_glob()` (imported above from
    `harness.common`) gives you the glob string for the Hive-partitioned
    lake under `data/parquet/category=<x>/part-0.parquet`; `hive_partitioning
    =true` re-exposes the partition directory's `category=<x>` segment as an
    ordinary `category` column in the query result.

    Filter to `in_stock` rows (a real boolean column in the Parquet files,
    not the partition column), `GROUP BY category`, `count(*)` and
    `avg(price)`. Run it via `con.execute(sql).fetchall()` (or whichever
    `duckdb` Python API method you prefer) and build the same `{category:
    (count, avg_price)}` shape `ch_answer` returns.

    This connection was just opened in this process: there is no
    long-running server behind it, no data pre-loaded into memory, no
    daemon to keep patched and provisioned. Every run pays for opening and
    scanning the Parquet files from scratch -- that cost (and how it
    compares to querying an already-running ClickHouse server) is exactly
    what this task's benchmark is measuring.
    """
    raise NotImplementedError
