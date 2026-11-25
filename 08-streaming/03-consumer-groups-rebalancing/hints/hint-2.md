The two callbacks you need are `on_assign(consumer, partitions)` and
`on_revoke(consumer, partitions)`, both passed to
`consumer.subscribe(topics, on_assign=..., on_revoke=...)`. `partitions` in
both is a list of `TopicPartition` objects — each has a `.partition`
attribute (the int you need for the log row) and a `.topic`.

Two things people miss:

- The callbacks are where you're expected to call `consumer.assign(partitions)`
  (in `on_assign`) and `consumer.unassign()` (in `on_revoke`) yourself. The
  default assignor does not do this for you — it's just telling you what
  happened; acting on it is your job. Skip it and your consumer never
  actually reads anything, even though the callbacks still fire.
- These callbacks run synchronously on the thread that calls `consumer.poll()`,
  during the `poll()` call that triggers the rebalance. A slow or blocking
  operation inside them (a Postgres insert is fine at this data volume, but
  keep it a plain synchronous `INSERT` per partition, not a batch job) delays
  the rest of the group's rebalance.

For the signal handling: register a handler for `SIGTERM` (and `SIGINT`, for
convenience when testing by hand) that just sets a module-level flag. Your
poll loop checks that flag each iteration and, once set, breaks and calls
`consumer.close()`. `close()` is a real Kafka LeaveGroup — it's what makes
member B's assignment settle in seconds instead of waiting out a session
timeout when member A later disappears in a test run.
