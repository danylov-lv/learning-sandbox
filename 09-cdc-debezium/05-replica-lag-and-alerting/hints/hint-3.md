Concretely, inside `main()`, after `ensure_ops_table(mart)` and after you
have both `mart` and `source` connections open:

- Get the total consumer lag for `(GROUP_ID, TOPIC)` from the one
  harness helper built for exactly this.
- Get the current WAL LSN from the source connection.
- Get the list of replication slots from the source connection, and pick
  out the one entry whose `slot_name` matches `SLOT_NAME`. If it's not
  there, something upstream (connector registration) hasn't happened yet --
  that's a real failure, not a case to silently paper over.
- Run one more query over the source connection that asks Postgres itself
  for the byte distance between the current LSN and that slot's
  `confirmed_flush_lsn` -- a cursor, one `SELECT`, one function call, one
  row, one column back.
- Compare the consumer lag total against `lag_threshold()` to get the
  alert boolean.
- `INSERT INTO ops.t05_lag_snapshots (consumer_lag, slot_lag_bytes, alert)
  VALUES (...)` on the mart connection, then `mart.commit()`.

What distinguishes the two phases this task is graded on isn't anything in
your monitor -- your monitor just measures whatever state it finds. Phase 1
sets up a topic where the materializer group's committed offsets already
equal the high watermark (so your consumer-lag call returns 0 no matter
when you run it). Phase 2 leaves a burst sitting on the topic that nothing
has committed against (so the same call returns a large number). Same
code, two different states of the world -- if your monitor is reading live
values off the two connections rather than hardcoding anything, it should
handle both without special-casing either.
