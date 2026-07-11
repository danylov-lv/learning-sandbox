# Hint 2

Go back to the actual numbers you produced:

- Task 05 gave you a Postgres-vs-ClickHouse ratio on the SAME per-category
  aggregate at 50M rows. What made Postgres slow — was it row count alone,
  or the absence of an index that a column store doesn't need in the same
  way? At what row count would that ratio stop mattering (i.e. Postgres
  would be "fast enough" regardless)?

- Task 07 gave you a DuckDB-vs-ClickHouse ratio on the SAME lake. Was
  DuckDB close, or far behind? If it was close, what does that say about
  when you'd bother running a ClickHouse server at all for a single-reader
  workload? If ClickHouse pulled ahead, under what condition did it do so —
  more concurrent queries? A query shape the primary index specifically
  helped with?

- Tasks 02, 03, and 04 gave you materialized views, ReplacingMergeTree, and
  TTL. Each of those is machinery ClickHouse runs FOR you continuously.
  DuckDB and Postgres don't have an equivalent for two of those. When is
  that machinery worth its complexity, and when would you rather just
  re-run a batch job by hand?

Now sketch, for each of the first three required sections, one or two
sentences that name a specific number or behavior you observed rather than
a generality.
