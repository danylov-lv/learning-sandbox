"""s09.t05 -- the same analytical aggregate on a row store and a columnar
engine.

You implement two functions that answer ONE question against the shared fact
table: for every category, over in-stock rows only, how many observations are
there and what is the average price? One function asks Postgres
(`price_history.observations`, deliberately index-light -- PK only), the other
asks ClickHouse (`price_history.observations_raw`, a MergeTree whose ORDER BY
is a sparse primary index). Same question, same data, two storage models.

Both functions MUST return the SAME shape so the validator can hold them to
the same answer key:

    { category: (count, avg_price) }

  * key    -- the category string (one of the 8 in ground truth)
  * count  -- int, number of rows with in_stock true in that category
  * avg    -- float, average price over those same rows

The validator compares BOTH results against `data/ground-truth.json`'s
`per_category_instock` (computed independently in numpy): count must match
exactly, avg within a small rounding tolerance. A fast wrong answer fails --
correctness is the primary gate. Only then does timing matter, and timing is
always relative to a baseline measured on THIS machine (see baseline.py).

Try it by hand before trusting the validator:

    uv run python baseline.py
    uv run python tests/validate.py
"""


def pg_answer(conn) -> dict:
    """Per-category (count, avg_price) over in-stock rows, computed in POSTGRES.

    `conn` is a live psycopg (v3) connection to `price_history` (given -- see
    baseline.py / the validator, which open it via harness `pg_connect()`).

    Query `price_history.observations`. Aggregate over the rows where
    `in_stock` is true, grouped by `category`. Return a dict mapping each
    category to a `(count, avg_price)` tuple:

        { "electronics": (19198591, 150.8147), ... }

    count is a Python int; avg_price is a Python float. Compute the average in
    the database (do not pull 40M rows into Python). The table carries only its
    primary key on `observation_id` -- there is no index on `category` or
    `in_stock`, so think about what plan Postgres is forced into here. That is
    the whole point of the comparison.
    """
    raise NotImplementedError


def ch_answer(client) -> dict:
    """Per-category (count, avg_price) over in-stock rows, computed in
    CLICKHOUSE -- the SAME answer as `pg_answer`, from the columnar engine.

    `client` is a live clickhouse-connect client on the `price_history`
    database (given -- opened via harness `ch_client()`).

    Query `observations_raw`. Aggregate over the rows where `in_stock` is set,
    grouped by `category`. Return the identical shape `pg_answer` returns:

        { category: (count, avg_price) }

    with count a Python int and avg_price a Python float. Note `in_stock` is a
    `UInt8` here (0/1), not a SQL boolean, and `category` is a
    `LowCardinality(String)`. Run the query with `client.query(...)` and read
    `result.result_rows` (a list of row tuples), or use the harness
    `ch_query(...)` helper. Compute the average in ClickHouse, not in Python.
    """
    raise NotImplementedError
