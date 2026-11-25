# 06 -- DuckDB on Parquet

## Backstory

Every task so far has meant standing up a server first -- ClickHouse
listening on a port, a database to connect to, a process to keep alive.
Sometimes that's the wrong amount of ceremony. Sometimes what you actually
have is a pile of Parquet files a scraper or an export job dropped on disk,
a laptop, and a question you want answered *right now* -- no container to
start, no user to provision, no schema to migrate. That's the case DuckDB is
built for: it's a library, not a service. You `import duckdb`, open an
in-memory connection, and point it straight at files on disk. There's
nothing else running.

The files in question here are the same fact table you've been querying in
ClickHouse, written instead as a **Hive-partitioned Parquet lake**:

```
data/parquet/
  category=electronics/part-0.parquet
  category=home-goods/part-0.parquet
  category=kitchen/part-0.parquet
  ... (8 partitions, one per category)
```

"Hive-partitioned" means the partition column (`category`) lives in the
*directory name*, not as a stored column inside each file -- a row in
`category=toys/part-0.parquet` has no `category` field in that file's own
schema; the value is implied entirely by which folder the file sits in.
DuckDB's `read_parquet(glob, hive_partitioning=true)` knows this convention:
it scans the glob, parses `category=<x>` back out of each path it finds, and
re-exposes `category` as an ordinary column in your query results -- as if
every row carried it, without anyone actually storing it eight times over.

That directory-per-category layout buys you something ClickHouse's MergeTree
ORDER BY bought you in task 01, by a completely different mechanism: if your
query filters on `category`, DuckDB doesn't have to open every file to
figure out which rows match -- the answer is sitting right there in the file
*path*, before a single byte of Parquet is decoded. That's **partition
pruning**, and it's the second half of this task. (The first half is just:
does querying files on disk give you the same answer as querying a database?
It has to, or none of this is useful.)

## What's given

- `src/lake.py` -- three functions, each taking a live DuckDB connection
  `con`. Rich docstrings explain exactly what each should query and return.
  All three currently `raise NotImplementedError`.
- The Parquet lake itself, already on disk at `data/parquet/category=<x>/
  part-0.parquet` (see the module README for how to (re)generate it at a
  chosen `SCALE` -- do not run the generator yourself for this task unless
  the lake is missing; a light scale like `0.01` is plenty).
- `harness/common.py`: `duckdb_connect()` (an in-memory DuckDB connection --
  no server, no file of its own) and `parquet_glob()` (the recursive glob
  string for the lake, e.g. `.../data/parquet/**/*.parquet`, to feed
  `read_parquet(...)`).
- `data/ground-truth.json`, the committed answer key, computed independently
  in numpy.

## What's required

Implement all three functions in `src/lake.py`:

1. **`per_category_instock(con)`** -- query the whole lake via
   `read_parquet(parquet_glob(), hive_partitioning=true)`, filter to
   `in_stock` rows, `GROUP BY category`, and return `{category: (count,
   avg_price)}`. Compute the aggregate in DuckDB, not in Python. Must match
   ground truth's `per_category_instock` -- this is the correctness gate.
2. **`one_category_files(con, category)`** -- the actual proof of partition
   pruning. Add `filename=true` to `read_parquet(...)` (a virtual column
   holding each row's source file path), filter `WHERE category = ...` on
   the *partition column*, and return the distinct file path(s) DuckDB
   touched. Filtered to one category, this should be exactly one file --
   proof DuckDB never opened the other seven partitions' files.
3. **`total_rows(con)`** -- `count(*)` over the entire lake, no filter. Must
   equal ground truth's `n_observations`.

Try your queries by hand before trusting the validator:

```bash
uv run python -c "
from harness.common import duckdb_connect
from src.lake import total_rows
print(total_rows(duckdb_connect()))
"
```

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Confirms the Parquet lake exists on disk (`NOT PASSED` with a
  regeneration hint if it's missing).
- Runs `total_rows()` and checks it equals `data/ground-truth.json`'s
  `n_observations` exactly.
- Runs `per_category_instock()` and checks every category's count (exact)
  and avg_price (within 0.01) against ground truth's `per_category_instock`,
  and that the category set matches exactly (no missing, no extra).
- Runs `one_category_files(con, "electronics")` and asserts it returns
  **exactly one** file path, and that the path contains
  `category=electronics` -- the structural proof that filtering on the
  partition column pruned the other 7 partitions instead of scanning all 8.
- Prints a `PASSED` message with the observed row count and the single
  pruned file path, or `NOT PASSED: <reason>` and exits 1 on any failure --
  including the lake being absent, a function still raising
  `NotImplementedError`, a wrong aggregate, or `one_category_files` touching
  more than one file.

## Estimated evenings

1

## Topics to read up on

- DuckDB's `read_parquet()` and the `hive_partitioning` option -- what it
  parses out of a `key=value` directory path and how it re-exposes that as
  a query-able column
- Partition pruning (skip whole files/directories based on path metadata)
  vs predicate pushdown (skip row groups *within* a file based on stored
  min/max statistics) -- two different mechanisms, both about reading less
  than everything
- Columnar Parquet internals: row groups, and the per-row-group column
  statistics (min/max) that let an engine skip a row group without
  decoding it
- `filename` (and other virtual/metadata columns DuckDB can attach to a
  scan) as a way to *observe* what a query actually touched, not just what
  it returned
- Zero-copy, in-process analytics: what changes (and what doesn't) when the
  "database" is a library call instead of a server you connect to

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers.
Don't read it before finishing this task.
