# 07 — DuckDB Taste

## Backstory

Every task so far has been a bespoke pyarrow script: hand-rolled JSONL
parsers, hand-rolled partition writers, hand-rolled pruning checks written
in Python because there was no query engine around to do it for you. The
analysts don't want any of that. They want to type SQL and get an answer,
the same way they'd hit any other table. They don't care that the "table"
is actually 18 directories of Parquet files sitting on local disk from task
04 — they just want `WHERE` clauses that work and don't take twenty
seconds.

DuckDB is the tool for this: an embedded OLAP engine that runs in the same
process as your script (or its own CLI), reads Parquet directly off disk or
object storage, and gets filter/projection pushdown and partition pruning
for free from a `read_parquet(...)` call — no ingestion step, no server to
stand up, not a byte of the lake moved or duplicated. You are going to point
it at task 04's lake and write four SQL queries that an analyst would
actually ask, then prove — not assume — that DuckDB is reading only the
files each query needs.

## What's given

- `data/lake/` — the hive-partitioned Parquet lake built in task 04
  (`month=YYYY-MM/part-*.parquet`, 18 partitions, zstd-compressed). This
  task only reads it; nothing here writes to it.
- `data/ground-truth.json` — same file every task in this module checks
  against. This task uses `rows_by_month`, `price_sum_by_month`,
  `filter_probe`, and `latest_price_probe`.
- `src/queries/` — four SQL files, each committed as a stub: a header
  comment stating its exact contract (inputs, required output columns and
  types, semantics), followed by a placeholder line. You replace the
  placeholder with a real query; the comment block stays.
- `tests/bench.py` — fully implemented. Runs your `probe.sql` through
  DuckDB and times it against a naive full-scan baseline (a plain
  `pyarrow.dataset` scan of the whole lake with no partition awareness,
  filtered in Python). Also runs `pruning_proof.sql` and parses its
  `EXPLAIN ANALYZE` plan for the number of physical Parquet files DuckDB
  actually opened. Writes `results-local.json`.
- `tests/validate.py` — the validator.

All four queries are executed by the test harness on a fresh DuckDB
connection that already has `SET TimeZone='UTC'` applied — don't put a
`SET` statement inside the `.sql` files themselves; each file is exactly
one query (or, for `pruning_proof.sql`, one `EXPLAIN ANALYZE` wrapping one
query). If you experiment in the DuckDB CLI directly, run `SET
TimeZone='UTC';` yourself first, or a query near a date boundary can return
a row count that's off by a handful — DuckDB compares your timestamp
literals in whatever session timezone it's currently in, and that is not
guaranteed to be UTC.

## What's required

Fill in the four files under `src/queries/`, replacing each
`-- TODO: write the query` line. Read each file's header comment for the
exact contract before writing anything.

1. **`monthly_rollup.sql`** — one row per month (`month`, `row_count`,
   `price_sum`), ordered by month.
2. **`probe.sql`** — reproduces `filter_probe` from ground truth: `source_id
   = 3`, `captured_at` covering 2025-09-01 through 2025-10-31 inclusive.
   Returns one row: `row_count`, `price_sum`. This range covers exactly two
   partitions (`month=2025-09`, `month=2025-10`) — write the `WHERE` clause
   so DuckDB prunes to those two files before opening anything else.
   Filtering on `captured_at` alone is not enough for pruning to happen:
   `captured_at` lives inside the Parquet files, the `month` value lives in
   the directory name, and only a filter that DuckDB can evaluate from the
   path can skip a file without opening it.
3. **`latest_prices.sql`** — for every product, the most recent
   observation with a non-null price: `product_id`, `captured_at_epoch`
   (Unix epoch seconds, UTC), `price`.
4. **`pruning_proof.sql`** — the same query as `probe.sql`, prefixed with
   `EXPLAIN ANALYZE`. `tests/bench.py` and `tests/validate.py` parse its
   profiled plan to find out how many files DuckDB actually read.

Then run, from the module root:

```bash
uv run python 07-duckdb-taste/tests/bench.py
uv run python 07-duckdb-taste/tests/validate.py
```

Fill in `NOTES.md`: how much faster was `probe.sql` than the naive
baseline, and was the gap what you expected for a 400k-row dataset (small
enough that a full scan is not actually slow in absolute terms — the point
here is the file-count story, not necessarily a dramatic wall-clock win)?
How many files did the pruned query read versus the naive baseline's 18?
What did you have to change in your `WHERE` clause to get pruning to
actually kick in, if your first attempt didn't?

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks:

- `monthly_rollup.sql`'s result matches `rows_by_month` and
  `price_sum_by_month` exactly (relative tolerance `1e-6` on sums) for all
  18 months, in month-ascending order;
- `probe.sql`'s result matches `filter_probe`'s `rows` and `price_sum`;
- `latest_prices.sql`'s result matches `latest_price_probe` for all 10
  listed `product_id`s (`captured_at_epoch` exact, `price` relative
  tolerance `1e-6`);
- a structural pruning check via `pruning_proof.sql`: the number of files
  DuckDB's `EXPLAIN ANALYZE` reports as actually read is no more than the
  number of `.parquet` files that physically exist on disk inside the two
  partition directories the probe covers, and strictly less than the
  lake's total file count — i.e. pruning demonstrably happened, not just a
  full scan that happened to return the right numbers;
- `results-local.json` exists (`tests/bench.py` was run);
- `NOTES.md` filled in beyond the template.

## Estimated evenings

1

## Topics to read up on

- Embedded OLAP vs client-server query engines — what "no server, no
  ingestion" actually buys and costs you
- `hive_partitioning` in `read_parquet` — how a directory-encoded column
  becomes a filterable, prunable column without living inside any file
- Filter pushdown vs projection pushdown
- Reading `EXPLAIN ANALYZE` output: what a `TABLE_SCAN` / `READ_PARQUET`
  node reports about files and row groups actually touched
- Window functions vs `arg_max()` for "latest row per group" queries
