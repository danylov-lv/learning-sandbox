# 03 — Consumer Groups and Rebalancing

## Backstory

In RabbitMQ, "scale out the consumers" means: add another process bound to
the same queue, and the broker round-robins messages across whichever
consumers are currently connected. No coordination step, no handoff, no
membership concept beyond "who's currently got a channel open." Kafka's
consumer groups look superficially similar — multiple processes sharing the
work of one topic — but the mechanism underneath is completely different,
and the difference has real consequences the first time you scale a
production consumer group under load.

A Kafka topic's partitions are divided up across the members of a consumer
group so that each partition is owned by exactly one member at a time. When
membership changes — a process joins, a process dies, a process is killed for
a deploy — the group coordinator runs a REBALANCE: it revokes partitions from
their current owners and reassigns the full partition set across the new
membership. Partition ownership is not fixed to the number of consumers you
started with; it moves. And because Kafka progress is tracked by offset
rather than by per-message ack, whatever a member was in the middle of
processing on a partition it's about to lose — if that work hasn't been
committed — gets reprocessed by whichever member ends up owning that
partition next. There is no equivalent "in-flight, unacked, will be requeued
to someone else" message-by-message story; the unit that moves is the whole
partition, and the boundary is the last committed offset, not the last
processed message.

This task makes you watch a rebalance happen. You instrument a consumer with
the rebalance callbacks confluent-kafka gives you, run one member, prove it
owns every partition, then start a second member in the same group and watch
the coordinator take partitions away from the first and hand them to the
second.

## What's given

- `src/consumer.py` — a scaffold for one consumer-group member. It ships:
  - the DDL for `ops.t03_rebalance_log` and a helper that creates the table
    if missing,
  - a `member_id()` helper that reads `S07_MEMBER_ID` from the environment
    (falling back to a random id if unset),
  - constants for the topic (`s07.t03.price-updates`) and group id
    (`t03-group`).
  - TODOs for everything else: the `on_assign` / `on_revoke` callbacks, the
    `Consumer` construction and `subscribe()` call, and the poll loop with
    SIGTERM handling.
- The stack: redpanda at `localhost:19092`, warehouse Postgres at
  `localhost:54307` (db `streaming`).
- `harness/common.py` — `kafka_bootstrap()`, `pg_connect()`, etc.

## What's required

1. Implement `on_assign(consumer, partitions)`: for each `TopicPartition` in
   `partitions`, insert one row into `ops.t03_rebalance_log` with
   `event='assign'`, `partition=<that partition's number>`,
   `member_id=<this process's member id>`. Then call
   `consumer.assign(partitions)` — with the default eager assignor,
   confluent-kafka does **not** call `assign()` for you inside the callback;
   you own that step.

2. Implement `on_revoke(consumer, partitions)` symmetrically:
   one `event='revoke'` row per partition, then `consumer.unassign()`.

3. Build the `Consumer` (at minimum `bootstrap.servers` and `group.id`,
   pick a sane `auto.offset.reset`) and `subscribe()` to
   `s07.t03.price-updates` passing both callbacks.

4. Write a poll loop: call `consumer.poll(timeout)` repeatedly — you don't
   need to do anything with the messages themselves for this task, just
   drain them so the group keeps making progress and doesn't look dead to
   the coordinator. Handle `SIGTERM` (a signal handler that sets a flag the
   loop checks) so the process exits its loop and calls `consumer.close()`
   cleanly. `consumer.close()` is what triggers a final `on_revoke` for
   whatever partitions this member still holds — skipping it leaves partial
   state in `ops.t03_rebalance_log` and (more importantly) leaves the group
   coordinator waiting out the full session timeout before it notices the
   member is gone.

5. Run it by hand first, from this task's directory:

   ```bash
   S07_MEMBER_ID=A uv run python src/consumer.py
   ```

   Confirm in `ops.t03_rebalance_log` (or Redpanda Console's consumer-group
   view at http://localhost:8307) that member A picks up all 6 partitions of
   `s07.t03.price-updates` (create the topic first if you haven't — the
   validator creates it for you, but for a manual test you'll need it too).
   Then, in a second terminal, run `S07_MEMBER_ID=B uv run python
   src/consumer.py` and watch the rebalance happen live: revoke rows for A,
   assign rows for A (its remaining share) and B.

## About the assignor and cooperative rebalancing

The default partition assignment strategy (`partition.assignment.strategy`,
default `range` or `roundrobin` depending on client defaults — check what
confluent-kafka picks) is "eager": every rebalance revokes ALL of a member's
partitions first (stop-the-world for that member), then reassigns the full
partition set across the current membership. That's what you're building and
observing here — you'll see `on_revoke` fire for partitions a member keeps
right before getting them back in the next `on_assign`.

Kafka also ships a `cooperative-sticky` assignor, which only revokes the
specific partitions that actually need to move, letting members keep
processing their unaffected partitions during the rebalance. It's worth
reading about even though this task doesn't require switching to it — the
contrast between "revoke everything, then reassign" and "revoke only what
moved" is the detail that matters when a rebalance happens on a
latency-sensitive consumer group in production.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It resets
the module's topics, creates `s07.t03.price-updates` with 6 partitions,
produces a batch of events, launches your `src/consumer.py` twice (member
`A`, then member `B`, both in group `t03-group`) as subprocesses, and reads
`ops.t03_rebalance_log` to check:

- member A initially gets assigned all 6 partitions,
- at least one `revoke` row exists once member B joins (proof the rebalance
  actually fired),
- the FINAL steady-state ownership — computed by replaying the assign/revoke
  sequence per member — is disjoint between A and B, together covers
  partitions `0..5`, and both members own at least one partition.

It terminates both subprocesses when it's done, pass or fail. Prints
`PASSED: ...` on success, `NOT PASSED: <reason>` and exits 1 otherwise —
including if your callbacks are never wired up (in which case it fails with
"consumer never recorded a partition assignment").

## Estimated evenings

1

## Topics to read up on

- Consumer groups: partition ownership, the group coordinator, the JoinGroup
  / SyncGroup protocol at a conceptual level
- Partition assignors: range, round-robin, sticky, cooperative-sticky —
  `partition.assignment.strategy`
- Eager vs incremental cooperative rebalancing — what "stop the world" means
  for the members NOT directly involved in a partition move
- `on_assign` / `on_revoke` callbacks in confluent-kafka, and why you have to
  call `assign()` / `unassign()` yourself inside them
- Offset commits and reprocessing: why uncommitted work on a revoked
  partition gets redone by its next owner, contrasted with RabbitMQ's
  per-message ack/nack/requeue model
- Consumer session timeouts / heartbeats and what makes the coordinator
  decide a member is gone
