"""s09.t06 -- DuckDB querying a Hive-partitioned Parquet lake, zero server.

The lake lives at `data/parquet/category=<x>/part-0.parquet` (8 partitions,
one per category), written with `pyarrow.dataset.write_dataset(...,
partitioning=["category"], partitioning_flavor="hive")`. Because it's
Hive-partitioned, the partition column (`category`) lives in the DIRECTORY
NAME, not inside the Parquet file itself -- a file under `category=toys/`
carries no `category` column in its own schema.

DuckDB's `read_parquet(glob, hive_partitioning=true)` stitches the lake back
together: it scans the glob, parses `category=<x>` out of each matching
path, and re-exposes `category` as an ordinary column in the result --
exactly as if every row had it, but without anyone having to store it
redundantly in every file.

`harness.common.parquet_glob()` gives you the exact glob string to feed in
(a recursive `.../data/parquet/**/*.parquet`). Every function below takes a
live, open DuckDB connection (`con`) -- the validator opens it via
`harness.common.duckdb_connect()` (an in-memory `:memory:` connection; no
server, no file, just a process that can read files off disk). Query
through `con.execute(sql).fetchall()` (or `.fetchone()` /
`.fetchnumpy()` / whatever `duckdb`'s Python API offers) -- do not open a
second connection of your own. You'll need `harness.common.parquet_glob()`
(import it yourself) to get the glob string for `read_parquet(...)`.
"""


def per_category_instock(con) -> dict:
    """Per-category (count, avg(price)) over in_stock rows, computed by
    DuckDB over the whole Parquet lake.

    Query `read_parquet('<glob>', hive_partitioning=true)` (glob from
    `parquet_glob()`), filter to `in_stock` rows, `GROUP BY category`, and
    compute `count(*)` and `avg(price)` IN THE SQL -- do not pull raw rows
    into Python and average them yourself; DuckDB's columnar engine is the
    thing being exercised here, not your own arithmetic.

    `in_stock` in the Parquet lake is a real column (not the partition
    column), stored as a boolean -- filter on it directly, e.g. `WHERE
    in_stock` or `WHERE in_stock = true`.

    Return a plain Python dict `{category: (count, avg_price)}`, one entry
    per category actually present in the lake (8 in the seeded corpus).
    `count` should be an int, `avg_price` a float.

    The validator compares this against `data/ground-truth.json`'s
    `per_category_instock`: every category's count must match EXACTLY, every
    avg_price within a small rounding tolerance, and the set of categories
    returned must match the set in ground truth (no missing, no extra).
    """
    raise NotImplementedError


def one_category_files(con, category: str) -> list:
    """The set of Parquet source file paths DuckDB actually reads to answer
    a query filtered to a single category -- the pruning proof.

    Because the lake is Hive-partitioned by `category`, all of one
    category's rows live in exactly one file, under
    `category=<that category>/part-0.parquet`. If DuckDB is told about the
    partitioning (`hive_partitioning=true`) and you filter `WHERE category =
    <category>` on the *partition column itself*, it can prune at the
    directory level before it ever opens a Parquet file for any other
    category -- it never has to inspect the other 7 partitions' files at
    all, let alone read their row groups.

    `read_parquet(..., hive_partitioning=true, filename=true)` adds a
    virtual `filename` column to the result holding each row's source file
    path. Query `SELECT DISTINCT filename FROM read_parquet(...) WHERE
    category = <category>` and collect the distinct paths into a Python
    list (or set -- return whichever, the validator only checks length and
    contents).

    `category` is a plain Python str (e.g. "electronics"); build the SQL
    with it directly (no untrusted input here) or bind it as a query
    parameter -- either works with DuckDB's Python API.

    Return the list/set of distinct file path strings observed. The
    validator asserts this returns EXACTLY ONE path, and that the path
    contains `category=<the category>` -- proof DuckDB pruned the other 7
    partitions instead of scanning the whole lake. If you get back more than
    one file, you likely filtered on something other than the partition
    column, or didn't pass `hive_partitioning=true`.
    """
    raise NotImplementedError


def total_rows(con) -> int:
    """Total row count across the entire Parquet lake (all 8 partitions,
    every row regardless of in_stock or category).

    Query `read_parquet('<glob>', hive_partitioning=true)` (glob from
    `parquet_glob()`) with a plain `count(*)` -- no WHERE clause. Return the
    count as a plain Python int.

    The validator asserts this equals `data/ground-truth.json`'s
    `n_observations` exactly -- the sanity check that the lake is complete
    (all 8 partition files present, none truncated) before the correctness
    and pruning checks even run.
    """
    raise NotImplementedError
