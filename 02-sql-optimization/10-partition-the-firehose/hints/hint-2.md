# Hint 2

Postgres has had declarative partitioning since v10: `CREATE TABLE ...
PARTITION BY RANGE (some_column)`, followed by one `CREATE TABLE ... 
PARTITION OF parent FOR VALUES FROM (...) TO (...)` per range. Once that's
set up, `DROP TABLE` (or `ALTER TABLE parent DETACH PARTITION ...`) on a
single partition removes an entire month in roughly constant time — no
row-by-row deletion at all. That's the retention win.

You cannot `ALTER TABLE inventory_events PARTITION BY ...` on an existing,
already-populated table directly — partitioning has to be baked in at
`CREATE TABLE` time. The standard move when you need to retrofit
partitioning onto a live table is: build a new, empty partitioned table
with the same columns, copy every row across (`INSERT ... SELECT`, or
`COPY` through an intermediate file for very large tables), then swap
names so the partitioned table takes over the original one's identity —
all inside one transaction so nothing else ever sees a half-migrated
state.

A `DEFAULT` partition would silently absorb any row that doesn't fit a
declared range — useful as a safety net, risky if you rely on it instead
of actually thinking through your date range, since a `DEFAULT` partition
that fills up becomes a de facto unpartitioned table again and blocks
adding new ranges that would overlap what it holds.

## Read up on

- Declarative partitioning mechanics: `PARTITION BY RANGE`, monthly
  children, the `DEFAULT` partition tradeoff
