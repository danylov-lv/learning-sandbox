# 06 — Lag Monitoring

## Backstory

In RabbitMQ, "is the consumer keeping up" is a question about **queue
depth** — the broker just tells you how many messages are sitting in the
queue right now, unacked. There's one number, it's on the broker's own
dashboard, and it goes up when producers outpace consumers and down when
they don't. Nothing to compute.

Kafka doesn't expose an equivalent number, because a Kafka topic isn't a
queue that drains — the log keeps every message whether or not a consumer
group has read it yet. "How far behind is this consumer group" is instead
a *relationship* between two things the broker tracks separately: the
**high watermark** (the offset of the next message that will be written
to a partition — everything before it exists in the log) and the group's
**committed offset** on that partition (the last offset it has
acknowledged processing). The difference, summed across partitions, is
consumer-group **lag**. It's not queue depth; it's a distance between two
independently-moving positions in an append-only log, and unlike queue
depth it is *per partition* before it's a total — a group can be badly
behind on one partition and caught up on the other five, and a single
number hides that.

This task builds the thing that turns that relationship into something you
can act on: a lag monitor that snapshots per-partition lag into Postgres
on demand and raises an alert when the total crosses a threshold. It's not
a consumer — it never reads a single message from the topic it's
monitoring. It only asks the broker two questions (what's the high
watermark on each partition, what has this group committed on each
partition) and does the subtraction.

## What's given

- `src/monitor.py` — a scaffold that:
  - Connects to Postgres and creates `ops.t06_lag_snapshots` and
    `ops.t06_alerts` if they don't exist — `ensure_ops_tables`, already
    written, not the point of the exercise.
  - Fixes `TOPIC = "s07.t06.price-updates"` and `GROUP_ID =
    "t06-consumer"`.
  - Reads the alert threshold from env var `S07_LAG_THRESHOLD` (default
    `50000`) via `lag_threshold()`, already written.
  - Ships `next_snapshot_id(conn)`, already written: each run appends a
    new snapshot rather than overwriting the last one.
  - Stops with `raise NotImplementedError` at the one place that matters:
    computing per-partition lag, persisting the breakdown, and deciding
    whether to alert.
- The stack from the module README: redpanda at `localhost:19092`,
  Postgres at `localhost:54307` (db `streaming`), `harness/common.py` for
  bootstrap/topic/pg helpers.

## What's required

1. Fill in `main()` in `src/monitor.py`. Per invocation (the script takes
   **exactly one snapshot and exits** — it is not a poll loop):
   - Call `harness.common.end_offsets(TOPIC)` — a dict `partition -> high
     watermark`.
   - Call `harness.common.committed_offsets(GROUP_ID, TOPIC)` — a dict
     `partition -> committed offset`, where a partition with no stored
     commit maps to `-1`.
   - For each partition: `lag = high - committed` if `committed >= 0`,
     else `lag = high` (no commit yet means the group's whole backlog on
     that partition is outstanding). Floor at 0.
   - Get a fresh `snapshot_id` from `next_snapshot_id(conn)` and insert
     one row per partition into `ops.t06_lag_snapshots`
     (`snapshot_id, topic, group_id, partition, high_watermark,
     committed_offset, lag`).
   - Sum the per-partition lag values into `total_lag`. If `total_lag >
     lag_threshold()`, insert one row into `ops.t06_alerts`
     (`snapshot_id, total_lag, threshold`).
   - Do all of the above in **one Postgres transaction** — one cursor,
     one `conn.commit()` at the end, so a snapshot is either fully
     written or not written at all.
2. **Do not use `harness.common.consumer_lag()` as your answer.** It's a
   *reference oracle* — it returns a single total integer, which is
   exactly the shape of information this task says is not enough. The
   validator uses it (indirectly, via the same primitives) to
   double-check your work, but your monitor has to persist a
   per-partition breakdown that a bare total can never reconstruct.
   Build lag from `end_offsets()` and `committed_offsets()` directly.
3. **psycopg gotcha on this build (3.x)**: do not use `with conn:` as a
   transaction context manager — on this version it can close the
   connection on `__exit__`, not just end the transaction. Use an
   explicit `cur = conn.cursor()` … `conn.commit()`, same as
   `ensure_ops_tables` already does.
4. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/monitor.py` from this task's directory.
   - Fixed topic `s07.t06.price-updates`, fixed group `t06-consumer`.
   - Reads `S07_LAG_THRESHOLD` from the environment (default `50000`).
   - Takes exactly one snapshot, writes it, exits `0`.
   - Never consumes a message from the topic — it only reads broker
     metadata for the group/topic pair.
   - Safe to run repeatedly — each run appends a new `snapshot_id`,
     never overwrites a previous one.

Try it by hand before trusting the validator (needs a topic and a group
with something committed against it — the validator sets both up for
you, but you can also poke at it with any topic/group you've created
yourself in earlier tasks by temporarily editing the constants):

```bash
uv run python src/monitor.py                       # takes one snapshot, exits 0
S07_LAG_THRESHOLD=10 uv run python src/monitor.py   # lower threshold, more likely to alert
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets `s07.t06.*` topics, creates `s07.t06.price-updates` (6
  partitions), drops `ops.t06_lag_snapshots` / `ops.t06_alerts` for a
  clean slate.
- Produces the first 100,000 events of the corpus, then commits the
  group's offsets to exactly the current high watermark on every
  partition (without consuming anything) — a deterministic way to put the
  group at zero lag as a known starting point.
- Runs your monitor once (`S07_LAG_THRESHOLD=50000`), expects exit `0`.
  Asserts: exactly one snapshot exists; its per-partition rows
  (`high_watermark`, `committed_offset`, `lag`) match an independent
  recomputation from `end_offsets()` / `committed_offsets()` taken right
  before the check; the sum of `lag` across partitions is `0`; no row
  in `ops.t06_alerts`.
- Produces the remaining ~100,000 events (high watermark rises, the
  group's committed offsets do not move — lag jumps by exactly the size
  of that second batch).
- Runs your monitor a second time (same threshold), expects exit `0`.
  Asserts: there are now exactly two snapshots; the new snapshot's
  per-partition rows again match an independent recomputation exactly;
  the summed lag equals the size of the second batch; exactly **one**
  alert row exists, referencing the second snapshot, with `total_lag`
  and `threshold` matching; the first snapshot still has no alert.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the monitor script is missing, either run exits nonzero or
times out, the tables never get created, a per-partition row doesn't
match the independent recomputation, or the alert bookkeeping is wrong
(missing, duplicated, or attached to the wrong snapshot).

## Estimated evenings

1

## Topics to read up on

- Consumer-group lag: high watermark vs committed offset, and why it's a
  per-partition quantity before it's a total
- Why a Kafka topic doesn't have a RabbitMQ-style "queue depth" — the log
  keeps messages whether or not any group has read them
- `AdminClient` / `Consumer.get_watermark_offsets` and
  `Consumer.committed` as read-only broker-metadata calls that don't
  require actually consuming anything
- What a committed offset of "none yet" (`OFFSET_INVALID`, surfaced here
  as `-1`) should mean for a lag computation
- Alerting design: why you'd persist a per-partition breakdown even
  though the alert decision itself only needs the total
