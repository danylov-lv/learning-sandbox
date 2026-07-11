"""s09.capstone CP2 -- cross-checking the serving layer against the lake.

CP1 built a ClickHouse serving layer and read a handful of aggregate answers
back out of it. Those answers should not be an artifact of anything
ClickHouse-specific -- they describe the underlying data, so an entirely
different engine, reading an entirely different physical copy of the data
(the Hive-partitioned Parquet lake at `data/parquet/category=<x>/`, not
`observations_raw`), must arrive at the exact same numbers. That is what
this checkpoint proves: DuckDB, querying files directly with no server at
all, reproduces `total_price_sum`, `per_category_instock`, and
`top_sellers` from CP1 -- because both are graded against the same
`data/ground-truth.json`, so agreement with ground truth on both sides
necessarily means the two engines agree with each other.

This checkpoint also proves the lake's partitioning does what it's supposed
to: filtering to one category should touch exactly one file on disk, not
scan all eight partitions to find the rows that match.

Every function takes a live, open DuckDB connection (`con`) -- the validator
opens it via `harness.common.duckdb_connect()`. Query through
`con.execute(sql).fetchall()` (or `.fetchone()` / whatever the `duckdb`
Python API offers) -- do not open a second connection of your own. Use
`harness.common.parquet_glob()` for the glob string
(`read_parquet(parquet_glob(), hive_partitioning=true)`), same as task 06.

No ClickHouse connection is needed anywhere in this file -- this checkpoint
is pure DuckDB-over-Parquet.

Try it by hand before trusting the validator:

    uv run python tests/validate_cp2.py
"""


def total_price_sum(con) -> float:
    """The grand total price sum over the WHOLE Parquet lake (all 8
    partitions, every row, no filter) -- the DuckDB-side counterpart to
    CP1's `build.total_price_sum`.

    Query `read_parquet(parquet_glob(), hive_partitioning=true)` with a
    single `sum(price)` aggregate. Return the result as a plain Python
    `float`.

    The validator compares this against `data/ground-truth.json`'s
    `price_sum`, within 0.01 -- the same number CP1's `total_price_sum`
    was checked against, now computed by a different engine over a
    different physical copy of the data.
    """
    raise NotImplementedError


def per_category_instock(con) -> dict:
    """Per-category `(count, avg_price)` over `in_stock` rows, computed by
    DuckDB over the whole Parquet lake -- identical shape to task 06's
    function of the same name and to CP1's `build.per_category_instock`.

    Query `read_parquet(parquet_glob(), hive_partitioning=true)`, filter to
    `in_stock` rows, `GROUP BY category`, and compute `count(*)` and
    `avg(price)` IN THE SQL.

    Return a plain Python `dict {category: (count, avg_price)}`, one entry
    per category present in the lake (8 in the seeded corpus). `count` an
    int, `avg_price` a float.

    The validator compares this against `data/ground-truth.json`'s
    `per_category_instock`: every category's `count` exact, `avg` within
    0.01, category set matching exactly.
    """
    raise NotImplementedError


def top_sellers(con) -> list:
    """The 10 sellers with the most observations across the whole Parquet
    lake, descending by count -- the DuckDB-side counterpart to CP1's
    `build.top_sellers`.

    `GROUP BY seller_id` over `read_parquet(parquet_glob(),
    hive_partitioning=true)`, order by the count descending, ties broken by
    `seller_id` ascending, limited to 10 rows.

    Return a list of `[seller_id, count]` pairs (or 2-tuples), in that
    order, both plain Python ints.

    The validator compares this list, in order, against
    `data/ground-truth.json`'s `top_sellers_by_count` -- the same list CP1's
    `top_sellers` was checked against.
    """
    raise NotImplementedError


def one_category_files(con, category: str) -> list:
    """The set of Parquet source file paths DuckDB actually reads to answer
    a query filtered to a single category -- the partition-pruning proof
    (identical contract to task 06's function of the same name).

    Because the lake is Hive-partitioned by `category`, all of one
    category's rows live in exactly one file, under
    `category=<that category>/part-0.parquet`. Filtering on the partition
    column itself (with `hive_partitioning=true` set) lets DuckDB prune at
    the directory level before opening a Parquet file for any other
    category.

    `read_parquet(..., hive_partitioning=true, filename=true)` adds a
    virtual `filename` column holding each row's source file path. Query
    `SELECT DISTINCT filename FROM read_parquet(...) WHERE category =
    <category>` and collect the distinct paths into a Python list (or set --
    the validator only checks length and contents).

    `category` is a plain Python str (e.g. `"electronics"`) -- build the SQL
    with it directly or bind it as a query parameter.

    Return the list/set of distinct file path strings observed. The
    validator asserts this is EXACTLY ONE path, and that the path contains
    `category=<the category>` -- proof the other 7 partitions were pruned,
    not scanned.
    """
    raise NotImplementedError
