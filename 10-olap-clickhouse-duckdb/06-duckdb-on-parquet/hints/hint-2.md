`read_parquet` takes its options as named arguments inside the call, DuckDB
SQL style: `read_parquet(<glob>, hive_partitioning=true)`. You can pass more
than one at once, e.g. `read_parquet(<glob>, hive_partitioning=true,
filename=true)` -- with `filename=true`, every row in the result gets an
extra `filename` column holding the path of the specific file it came from.
That's your instrument for `one_category_files`: don't try to inspect
DuckDB's query plan or profiling output to figure out which files got
touched -- just ask the data itself where it came from, with `SELECT
DISTINCT filename ... WHERE category = <category>`.

Why does filtering on `category` (the *partition* column) let DuckDB skip
files entirely, when filtering on some other column wouldn't? Because with
Hive partitioning, DuckDB knows the value of `category` for an entire file
before it opens it -- it's encoded in the folder name it already had to list
to build the glob. A filter on `category` is something DuckDB can evaluate
against *path strings*, zero I/O, and then simply never call `open()` on the
files that don't match. A filter on `price` or `in_stock`, by contrast,
requires opening the file (though Parquet's own row-group statistics can
still let DuckDB skip chunks *inside* an opened file -- that's predicate
pushdown, a related but different trick from partition pruning).

For `per_category_instock`, remember this is standard SQL over the result of
`read_parquet(...)` treated as a table: `SELECT category, count(*), avg(price)
FROM read_parquet(...) WHERE in_stock GROUP BY category`. `in_stock` in this
Parquet schema is a real boolean column (unlike ClickHouse's `UInt8` in task
01) -- you can filter on it directly with `WHERE in_stock`, no `= 1` needed
(though `= true` also works if you prefer to spell it out).
