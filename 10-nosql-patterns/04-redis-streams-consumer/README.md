# 04 -- Redis Streams Consumer Group

## Backstory

A price-update stream feeds a pool of scraper workers: each entry is one
scraped price observation, and a pool of consumer processes pulls entries off
the stream, does some work with each one (write it somewhere, recompute an
aggregate, whatever), and moves on. Workers die. A process gets OOM-killed
mid-batch, a container gets rescheduled, a laptop lid closes on a dev running
one locally -- whatever the cause, at some point a worker will have read a
batch of entries and not yet finished acknowledging them when it stops
responding for good. The requirement is simple to state and easy to get
wrong: that worker's in-flight entries must not be lost. Some other worker in
the pool must be able to notice they're stuck, take them over, and finish
them -- without double-claiming work that a *still-alive, still-busy* worker
legitimately holds.

## Contrast with what you already know

You've run RabbitMQ and/or Kafka. Redis Streams sits in an odd spot between
them, and the differences are exactly what this task is about:

- **Like a Kafka topic**: a stream is an append-only log with a monotonic ID
  per entry; entries aren't deleted on read; multiple consumer groups can
  each read the whole stream independently; a group can replay history by
  reading from an ID other than "now".
- **Unlike Kafka, like an RMQ queue**: within one consumer group, delivery is
  tracked per ENTRY, not per OFFSET. Reading an entry with `XREADGROUP`
  files it into that group's Pending Entries List (PEL) -- effectively "this
  specific message is checked out to this specific consumer, unacknowledged"
  -- and it stays there, individually, until something `XACK`s it. There is
  no single number ("committed offset N") that implicitly marks everything
  up to N as done; every entry is tracked and retired on its own.
- **Recovery is per-message, not per-partition.** In Kafka, a crashed
  consumer's *partition* gets reassigned during a rebalance, and the new
  owner resumes from the last committed offset -- coarse, and it can
  re-process entries the dead consumer actually finished but hadn't
  committed yet. In Streams, another consumer inspects the PEL directly,
  finds the specific entries that have been idle (unacked) longer than some
  threshold, and reclaims exactly those -- nothing coarser than "the messages
  that are actually stuck."
- **Ack semantics**: RMQ acks/nacks a delivered message and the broker can
  requeue it. Streams' `XACK` is closer to that than to a Kafka offset commit
  -- but nothing "requeues" an unacked Streams entry automatically; it just
  sits in the PEL until a consumer explicitly claims it (`XCLAIM` /
  `XAUTOCLAIM`), which is a pull-based, any-consumer-can-take-it recovery
  rather than a broker-pushed redelivery.

## What's given

- `src/consumer.py` -- five functions, each with a docstring that spells out
  the exact Redis command, wire format, and return shape expected. All five
  currently `raise NotImplementedError`.
- The live stack: Redis (with the RedisBloom module, unused here) on
  `localhost:6310` via `harness.common.redis_client()`. No password.
- `data/events.json` (gitignored, already generated) -- NDJSON scrape events;
  the validator reads a slice of it directly as the workload. You don't need
  to regenerate anything or load a database yourself for this task.

## What's required

Implement all five functions in `src/consumer.py`:

1. **`produce(client, stream_key, events)`** -- `XADD` each event dict onto
   the stream, one field `"payload"` holding `json.dumps(event)`.
2. **`ensure_group(client, stream_key, group)`** -- `XGROUP CREATE ... MKSTREAM`,
   tolerating `BUSYGROUP` if the group already exists.
3. **`consume_new(client, stream_key, group, consumer, count)`** -- `XREADGROUP`
   with `">"` to read up to `count` never-before-delivered entries, returned
   as `(entry_id, fields)` tuples, LEAVING them pending (unacked) in the PEL.
4. **`ack(client, stream_key, group, entry_ids)`** -- `XACK` the given entry
   IDs, returning how many were actually acked.
5. **`reclaim(client, stream_key, group, consumer, min_idle_ms, count)`** --
   `XAUTOCLAIM` (preferred) or `XPENDING` + `XCLAIM`, to steal up to `count`
   entries idle at least `min_idle_ms` from ANY consumer in the group and
   reassign them to `consumer`, returned in the same `(entry_id, fields)`
   shape.

Keys under `s10:t04:` (e.g. `s10:t04:stream` for the stream key). Rich
docstrings on every function spell out exact Redis commands and return
shapes -- read them before reaching for the hints.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It produces 2000 events onto the stream, has a consumer `c1` read a batch and
then simulates a crash (simply never acking -- exactly what a dead consumer
looks like from Redis's side), has a consumer `c2` `reclaim` those stranded
entries and finish them, then has `c2` drain the rest of the stream normally.
It checks, all independent of wall-clock timing:

- **PEL bookkeeping, both directions**: right after `consume_new` (before any
  ack), the delivered entries show up in `XPENDING`; right after `ack`, they
  no longer do.
- **Reclaim recovers ALL of a dead consumer's stranded work** -- not some of
  it, not a re-read of already-acked entries.
- **No loss (at-least-once)**: the set of distinct `event_id`s processed
  (recovered via reclaim, plus everything read directly) equals the full set
  of produced `event_id`s -- exactly, no missing, no extras.
- **PEL fully drained** at the end: `XPENDING`'s summary shows zero pending.

Prints `PASSED` with the counts observed, or `NOT PASSED: <reason>` and exits
1 on any failure -- including a still-stubbed function, a wrong wire format,
or the stack being down.

## Estimated evenings

1-2

## Topics to read up on

- Redis Streams as an append-only log: `XADD`, entry IDs, `XRANGE` vs
  `XREAD` vs `XREADGROUP`
- Consumer groups and the Pending Entries List (PEL): what `XREADGROUP`'s
  `">"` means vs a concrete last-delivered-ID, and why reading is not the
  same as finishing
- `XACK` -- per-message acknowledgement, and why there's no single "offset"
  that retires a whole prefix at once
- `XPENDING` (summary form and range form) for inspecting who's holding what,
  and for how long
- `XCLAIM` and `XAUTOCLAIM`, and `min-idle-time` -- how a live consumer takes
  over another consumer's stuck-in-flight entries without racing a consumer
  that's simply still busy
- At-least-once delivery and why the *consumer* of this queue (not the queue
  itself) is responsible for idempotency if redelivery must never double-apply
  an effect
- How this differs from a Kafka consumer group rebalance (partition-level,
  offset-resume) and from an RMQ nack/requeue (broker-pushed, no PEL to
  inspect)

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers. Don't
read it before finishing this task.
