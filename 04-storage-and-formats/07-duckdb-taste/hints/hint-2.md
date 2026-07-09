# Hint 2

Why doesn't filtering only on `captured_at` prune anything? Because
`captured_at` is a real column stored inside every Parquet file's row
groups. DuckDB *can* use row-group-level min/max statistics to skip a row
group without reading it — that's a different, finer-grained kind of
pruning than partition pruning, and it happens after the file is already
opened and its metadata read. But the directory listing itself doesn't
know anything about `captured_at`'s values ahead of time, so every one of
the 18 files gets opened and its footer inspected before any row-group
skipping can even be considered. Partition pruning happens one level
earlier, purely from the file paths DuckDB decides to open in the first
place — and the only column DuckDB can evaluate from a path alone is the
one hive_partitioning exposed from that path: `month`.

So: your `probe.sql` needs a condition on `month` itself, not just on
`captured_at`. Given the probe's date range (2025-09-01 through 2025-10-31
inclusive), which two literal month values does that range touch? Write
that as an explicit `month IN (...)` (or equivalent) alongside your
`source_id` and `captured_at` conditions — all three can coexist in the
same `WHERE` clause.

For `latest_prices.sql`, "latest row per group" has two idiomatic shapes in
SQL:

- A window function: `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY
  captured_at DESC)`, then keep rows where that number is 1. This computes
  and materializes a rank for every single row before filtering — general,
  but it does more work than it strictly needs to for this specific
  question.
- `arg_max(price, captured_at)` (and `arg_max(captured_at, captured_at)`
  for the timestamp itself) in a `GROUP BY product_id`. This asks DuckDB
  for exactly "the price at the row where captured_at was highest" without
  ever materializing a full ranking — usually the more direct tool when
  the question really is just "give me the row with the max of some
  column, per group," rather than "give me the whole order."

Either passes the validator. Try to reason about which one is doing less
unnecessary work for what you're actually asking, not just which one you
remembered first.
