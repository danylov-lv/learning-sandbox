-- Task 10: partition the firehose.
--
-- inventory_events is a 9M-row, append-heavy time series. Every ops query
-- filters a recent window; monthly retention DELETEs are slow and leave
-- bloat (450k dead tuples already, per seed/schema.sql's comment on
-- defect (c)). Migrate it to monthly RANGE partitions so retention becomes
-- DROP/DETACH and recent-window queries prune to the partitions that
-- matter.
--
-- Requirements (see README.md for the full brief):
--   - A single transactional script: BEGIN; ... COMMIT; -- run with psql
--     or any client that executes it as one script.
--   - PARTITION BY RANGE (occurred_at), monthly boundaries, covering the
--     table's full time span PLUS at least one wholly future month.
--   - Move all 9M rows across (INSERT ... SELECT or equivalent).
--   - End with the partitioned table actually named inventory_events
--     (swap names), with useful indexes recreated (partitioned-table
--     indexes propagate to each partition automatically).
--   - Touch inventory_events only. No DDL/DML on any other table.
--
-- This file is not run for you -- apply it against the live database
-- yourself (e.g. `psql ... -f src/migrate.sql`), then run
-- tests/check.py to verify.
--
-- TODO: write your migration here.
BEGIN;

-- (stub)

COMMIT;
