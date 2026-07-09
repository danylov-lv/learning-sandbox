# Hint 1

`read_parquet(pattern, hive_partitioning=true)` is the whole surface area
you need for the first two queries. Point it at a glob covering every
partition (`data/lake/*/*.parquet`), turn on `hive_partitioning`, and the
`month` value encoded in each directory name (`month=2025-09/`) shows up as
an ordinary queryable column called `month` — even though no byte of it
exists inside any Parquet file. That is the entire mechanism this task is
built around: a value that lives in a path, not in a file, and a query
engine that reads the path before it reads anything else.

Ask yourself, before writing `probe.sql`: if DuckDB doesn't know a value
lives in the path, what does it have to do to find out which rows match
your `WHERE` clause? What would it have to do differently if it did know?
That difference is what `EXPLAIN ANALYZE` is for — you'll use it directly
in `pruning_proof.sql`, but it's worth running by hand on `probe.sql`
first, informally, before you commit to a final `WHERE` clause.

`monthly_rollup.sql` doesn't need `EXPLAIN ANALYZE` at all — it's a
straightforward `GROUP BY` over the whole lake. Get that one working first;
it'll confirm your `read_parquet(...)` call and schema understanding are
right before you build the trickier probe query on top of the same base.
