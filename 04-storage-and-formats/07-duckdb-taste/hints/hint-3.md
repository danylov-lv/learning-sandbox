# Hint 3

Concrete pieces, not full queries:

- `read_parquet('data/lake/*/*.parquet', hive_partitioning=true)` for all
  four files. Every query in this task reads the same glob.
- `month` is a string like `'2025-09'`. A range like September through
  October is just `month IN ('2025-09', '2025-10')` — you don't need date
  arithmetic on the partition column, only on `captured_at` (the exact
  boundary you need there: `captured_at >= TIMESTAMP '2025-09-01'` and
  `captured_at < TIMESTAMP '2025-11-01'` — one day past the inclusive end
  date, so the last day of October is fully included without an
  off-by-one).
- `epoch(captured_at)` returns the Unix epoch as a `DOUBLE`; cast it —
  `epoch(captured_at)::BIGINT` — to get an integer number of seconds, which
  is what `captured_at_epoch` in ground truth is.
- A row is a "failed scrape, no price observed" row exactly when `price IS
  NULL`. Filter those out (`WHERE price IS NOT NULL`) before computing
  "latest" — either inside the window/aggregate query directly, or as an
  earlier `WHERE` on the same `FROM read_parquet(...)`.
- `pruning_proof.sql` is not a new query — it's `EXPLAIN ANALYZE` followed
  by literally the same `SELECT` you already wrote in `probe.sql`. Copy it
  over rather than rederiving it; if the two ever drift apart, the file
  count `pruning_proof.sql` reports stops meaning anything about
  `probe.sql`.
- `SUM(price)` and `COUNT(*)` in the same `SELECT` give you both required
  output columns for `probe.sql` and each row of `monthly_rollup.sql` in
  one pass — no need for a subquery or a second query for the count.
