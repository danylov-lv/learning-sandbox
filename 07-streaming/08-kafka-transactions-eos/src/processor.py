"""s07.t08 processor -- transactional read-process-write, topic-to-topic
exactly-once.

CLI contract (what the validator relies on):

    uv run python src/processor.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t08-processor").
- Producer transactional.id is fixed: TRANSACTIONAL_ID below
  ("s07-t08-eos") -- needed so a restarted process fences off any zombie
  instance of itself still holding a previous, uncommitted transaction.
- Reads TOPIC ("s07.t08.price-updates"), writes OUTPUT_TOPIC
  ("s07.t08.enriched"): one transformed output record per input event, see
  transform_event() below.
- Honors env var S07_CRASH_AFTER: if set, the process hard-exits via
  os._exit(1) right after processing that many messages THIS RUN, from
  INSIDE an open Kafka transaction. See _maybe_crash below -- it is a TEST
  HOOK, already implemented, not something you write.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught
  up with the topic).
- Must be SAFE TO RUN REPEATEDLY, including resuming right after the
  crash hook aborted a transaction mid-batch: no input event may be
  skipped, and no output record from an aborted transaction may ever
  become visible to a read_committed consumer.

The problem in one sentence: task 04 made an aggregate exactly-once by
tucking the atomicity into Postgres, because Kafka itself only promises
at-least-once against a plain manual-commit consumer. Here there is no
Postgres -- the "downstream system" is another Kafka topic. Kafka solves
that with its own transactions: a transactional producer can atomically
bundle the records it produces AND the input offsets it consumed into ONE
transaction, via send_offsets_to_transaction. A crash mid-transaction
leaves that transaction unfinished; on restart, the broker's transaction
coordinator (with help from init_transactions' fencing) ensures it never
commits, and a read_committed consumer of the output never sees any of
its records. Nothing was lost either -- the input offsets from that
aborted transaction were never advanced, so the same input gets
reprocessed and this time committed for real.

The recipe:

    init_transactions()                          # ONCE, before the loop

    # per batch of up to BATCH_SIZE consumed records:
    begin_transaction()
    for each consumed record:
        produce(OUTPUT_TOPIC, transform_event(record))
    send_offsets_to_transaction(
        consumer.position(consumer.assignment()),
        consumer.consumer_group_metadata(),
    )
    commit_transaction()                          # or abort_transaction()
                                                    # on any error in the batch

Why not one transaction per message? At 200k events, a Kafka transaction
is a multi-round-trip protocol operation (begin, produce acks,
send_offsets_to_transaction, a two-phase commit-marker write). Paying that
cost once per message instead of once per BATCH_SIZE is the difference
between finishing in seconds and taking long enough to make this exercise
painful for no pedagogical benefit. Batch it.

Try it yourself before running the validator:

    S07_CRASH_AFTER=70000 uv run python src/processor.py   # dies mid-transaction
    uv run python src/processor.py                         # resumes, catches up
    uv run python src/processor.py                         # rerun with nothing new
"""

import json
import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap  # noqa: E402

TOPIC = "s07.t08.price-updates"
OUTPUT_TOPIC = "s07.t08.enriched"
GROUP_ID = "t08-processor"
TRANSACTIONAL_ID = "s07-t08-eos"
BATCH_SIZE = 5000
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0


def transform_event(event: dict) -> dict:
    """Given plumbing. A deliberately boring, non-identity transform -- the
    point of this task is the transaction boundary, not this function.
    Grading is on the set of `seq` values that arrive downstream exactly
    once, not on this transform's business meaning."""
    return {
        "seq": event["seq"],
        "product_id": event["product_id"],
        "category": event["category"],
        "price": event["price"],
        "price_cents": round(event["price"] * 100),
    }


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S07_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it. Call this from INSIDE an open transaction
    -- after producing some of the current batch's output records, before
    commit_transaction() -- so the crash actually aborts a
    transaction-in-flight (the exact window this task is graded on),
    rather than landing cleanly between batches where there'd be nothing
    interesting to prove.
    """
    crash_after = os.environ.get("S07_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def main() -> None:
    from confluent_kafka import Consumer, Producer

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        # Short session timeout so a crashed member is evicted from the group
        # quickly -- a restarted process would otherwise wait out the default
        # 45s session timeout before the broker reassigns its partitions.
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    })
    consumer.subscribe([TOPIC])

    producer = Producer({
        "bootstrap.servers": kafka_bootstrap(),
        # Fixed transactional.id: on restart after a crash, this lets the
        # broker recognize "this is the same logical producer as before"
        # and fence off (bump the epoch on) any zombie instance still
        # holding the previous, now-abandoned transaction.
        "transactional.id": TRANSACTIONAL_ID,
    })

    processed = 0
    idle_seconds = 0.0

    try:
        # TODO: init_transactions() ONCE here, before the loop.

        while idle_seconds < IDLE_EXIT_SECONDS:
            msg = consumer.poll(POLL_TIMEOUT_SECONDS)
            if msg is None:
                idle_seconds += POLL_TIMEOUT_SECONDS
                continue
            if msg.error():
                idle_seconds = 0.0
                continue
            idle_seconds = 0.0

            event = json.loads(msg.value())

            # TODO: batch up to BATCH_SIZE consumed records per Kafka
            # transaction. Rough shape per batch:
            #
            #   1. producer.begin_transaction()
            #   2. For each consumed record in this batch: transform it
            #      with transform_event() and producer.produce(
            #      OUTPUT_TOPIC, value=..., key=str(product_id).encode()).
            #   3. producer.send_offsets_to_transaction(
            #        consumer.position(consumer.assignment()),
            #        consumer.consumer_group_metadata(),
            #      )
            #      -- this ties the consumer's input offsets into the SAME
            #      transaction as the output records. Do NOT call
            #      consumer.commit() anywhere in this task; this call
            #      replaces it.
            #   4. processed += 1; _maybe_crash(processed) -- call this
            #      INSIDE the open transaction, e.g. right after step 2
            #      for the current record, before step 5's commit.
            #   5. producer.commit_transaction() to close out the batch,
            #      or producer.abort_transaction() if anything in the
            #      batch raised.
            #
            # A single record's worth of code per poll() is fine; just
            # make sure begin_transaction() happens once per batch (not
            # once per message) and commit_transaction()/
            # send_offsets_to_transaction() happen once the batch reaches
            # BATCH_SIZE (or you decide to flush early).
            raise NotImplementedError
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
