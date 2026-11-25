Consumer lag: you don't need to touch offsets or watermarks by hand for
this task. `harness/common.py` already has a function that returns the
total lag (summed across partitions) for a `(group, topic)` pair -- look at
its signature and use it directly.

Slot lag bytes: `replication_slots(conn)` (called against the SOURCE
connection) returns one dict per replication slot in `pg_replication_slots`,
including `confirmed_flush_lsn`. `source_current_lsn(conn)` returns the
source's current WAL LSN, `pg_current_wal_lsn()`. Postgres represents LSNs
as opaque `pg/pg` hex pairs, not plain integers -- don't try to parse or
subtract them in Python. Postgres itself exposes the byte-distance between
two LSNs as a SQL function you can call from a query:
`pg_wal_lsn_diff(lsn_a, lsn_b)`. Run that over the SOURCE connection with
the current LSN and the slot's `confirmed_flush_lsn` as arguments.

Filter `replication_slots(conn)`'s result down to the row where
`slot_name == SLOT_NAME` before reading its `confirmed_flush_lsn` -- other
slots (from other tasks, or leftover from a previous run) may exist on the
same source.

Alert: strictly greater than the threshold, not greater-or-equal -- a
snapshot sitting exactly at the threshold should not alert.
