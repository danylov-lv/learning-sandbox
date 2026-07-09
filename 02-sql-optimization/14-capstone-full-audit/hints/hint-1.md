# Hint 1

Structure the audit the same way you'd structure it on a real job: workload
first, catalogs second, fixes last. Don't start writing DDL the moment you
spot something ugly in `pg_indexes` — you don't yet know whether that ugly
thing is actually costing you anything on a query anyone runs.

Concretely: run all eight `workload/qcNN.sql` queries with `EXPLAIN
(ANALYZE, BUFFERS)` before you touch anything else. Only once you have all
eight plans and their baselines in front of you should you start cross-
referencing them against `pg_indexes`, `pg_stat_user_tables`, and
`pg_stats`. The database's problems are a fixed, small set (this module has
been teaching you them one at a time); the workload tells you which of them
actually matter *for this specific set of queries* and in what order.
