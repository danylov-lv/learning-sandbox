# 01 — Log vs Queue, and Offsets

## Backstory

You've operated RabbitMQ for years. A message arrives on a queue, exactly one
competing consumer picks it up, that consumer acks it, and the broker deletes
it. That's the whole lifecycle: publish, deliver once, ack, gone. It's a great
model for work distribution — jobs, tasks, one-shot commands — and a bad model
for something a new requirement just landed on your desk: the pricing team
wants their own independent read of every price-update event without stealing
any from the team that's already consuming them, and separately, someone wants
to replay last hour's price stream through a brand-new model that didn't exist
when the events first arrived. Neither of those is expressible in a queue.
Once a message is acked, RabbitMQ's job is done — there's no "read it again"
and no "give a second team the same messages the first team already consumed."

Kafka (here, redpanda, which speaks the Kafka protocol) starts from a
different premise: a topic partition is an append-only, retained **log**, not
a queue. Publishing appends a record at the next **offset**. Nothing is
deleted when it's read — retention is time/size-based, independent of who's
consumed what. A **consumer group** is not "the pool of workers competing for
a queue's messages"; it's one independent cursor position (a group id plus a
committed offset per partition) into the *same* shared log. Point a second,
distinct consumer group at the same topic and it reads every record from
scratch — it isn't competing with the first group for messages, because
nothing was ever "claimed." Point a *new* group at offset 0 and you've just
replayed history. This task makes you build the smallest possible example of
both: publish once, then prove two independent groups each see everything, and
prove a fresh group can rewind and see it all again.

## What's given

- `src/producer.py` — scaffold. TODO: create the topic if needed, then publish
  every event in `data/events.ndjson` to `s07.t01.price-updates`, keyed by
  `product_id`, using `confluent_kafka.Producer`.
- `src/read_history.py` — scaffold. TODO: given a consumer group id on the
  command line, consume `s07.t01.price-updates` from the beginning under that
  group and print how many messages were read. Run it twice with two
  different group ids and watch both print the same count; run it a third
  time with a group id you've already used and watch it read (close to)
  nothing, because that group's committed offset is already past the end.
- The corpus: `data/events.ndjson` (~200k price-update events, one JSON object
  per line) and its answer key `data/ground-truth.json`.
- `harness/common.py` (`../harness/common.py` from this directory) — the same
  helpers the validator uses: `kafka_bootstrap()`, `create_topic()`,
  `end_offsets()`, `drain()`, etc. You're free to use them in your own
  scripts, except where a docstring says otherwise (`produce_events()` is
  reserved for the validator's independent check — write your own produce
  loop in `producer.py`).

## What's required

1. Implement `src/producer.py`: publish the entire corpus, in order, to
   `s07.t01.price-updates`, keyed by `product_id` (string-encoded). Create the
   topic with 6 partitions first if it doesn't exist yet — either
   `harness.common.create_topic("s07.t01.price-updates", partitions=6)` or
   your own `confluent_kafka.admin.AdminClient` + `NewTopic` call, your
   choice. Run it:

   ```
   uv run python src/producer.py
   ```

2. Implement `src/read_history.py`: consume the topic from the beginning
   under a caller-supplied consumer group and print the count. Run it at
   least twice, with two different group ids, and once more reusing one of
   those group ids, to see the fan-out and the "already consumed" behavior
   with your own eyes before the validator checks it independently:

   ```
   uv run python src/read_history.py demo-group-1
   uv run python src/read_history.py demo-group-2
   uv run python src/read_history.py demo-group-1
   ```

3. Fill in `NOTES.md`'s "Log vs queue: written comparison" section. This is a
   graded deliverable, not busywork — see Completion criteria.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It does
**not** trust your producer's own printed counts — it independently:

- Requires the topic `s07.t01.price-updates` to exist and hold exactly
  `total_events` messages (ground truth), summed across partitions via high
  watermarks.
- Drains the topic under three separate, freshly-generated consumer groups
  (each with a random suffix, so none has ever been used before) and asserts
  each one reads exactly `total_events` messages — proving fan-out (two
  independent groups both see the whole log) and replay (a third fresh group,
  read again from offset 0, sees it all too).
- Samples ~200 messages and asserts every key is non-null; across the full
  topic, asserts every distinct `product_id` key lands on exactly one
  partition (key-based routing) and that the count of distinct `product_id`
  keys equals ground truth's `distinct_products_with_events`.
- Requires `NOTES.md`'s "Log vs queue: written comparison" section to be
  filled in with real content (at least ~600 characters, discussing offsets,
  acks, consumer groups, competing consumers, and replay by name).

Fails gracefully with `NOT PASSED: <reason>` (exit 1, no traceback) if the
topic is missing, under-populated, mis-keyed, or the notes are still the
template.

## Estimated evenings

1

## Topics to read up on

- Kafka's log abstraction: partitions, offsets, append-only writes, retention
- Consumer groups: what a group id means, per-partition committed offsets,
  partition assignment within a group
- Why two different consumer groups reading the same topic don't compete —
  and why RabbitMQ's competing consumers on one queue is the opposite model
- Message keys and partition routing (`hash(key) % partitions`, roughly) —
  why keying by `product_id` matters for anything that needs per-product
  ordering later in this module
- Retention and replay: what makes "seek a new group to offset 0" possible in
  Kafka and impossible once a RabbitMQ message is acked
