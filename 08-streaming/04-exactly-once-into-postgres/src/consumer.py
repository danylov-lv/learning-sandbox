"""s07.t04 consumer -- exactly-once aggregation into Postgres.

CLI contract (what the validator relies on):

    uv run python src/consumer.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t04-consumer").
- Subscribes to topic TOPIC ("s07.t04.price-updates").
- Maintains core.t04_category_totals(category, cnt, price_sum): for every
  event in the corpus, exactly once, cnt += 1 and price_sum += price for
  that event's category -- no matter how many times Kafka redelivers the
  event.
- Honors env var S07_CRASH_AFTER: if set, the process hard-exits via
  os._exit(1) right after processing that many messages THIS RUN, without
  finishing whatever commit (Postgres or Kafka) was in flight. See
  _maybe_crash below -- it is a TEST HOOK, already implemented, not
  something you write.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic) -- this is how the validator knows a run finished.
- Must be SAFE TO RUN REPEATEDLY: a fresh run after a crash, or a run
  against an empty table, must converge on the exact same totals as an
  uninterrupted run. That is the actual point of this task -- task 02
  already proved at-least-once delivery; this task proves you can build an
  exactly-once *aggregate* on top of it.

The problem in one sentence: Kafka guarantees at-least-once (task 02). A
consumer that crashes AFTER updating core.t04_category_totals but BEFORE
committing its Kafka offset will see that same message again on restart.
`cnt += 1; price_sum += price` applied a second time for the same event is
a silent over-count -- the aggregate drifts and there is no way to tell
from the table alone that it happened. You need to make "apply this
event's delta" and "remember that I applied it" a single atomic unit, so a
crash anywhere in the loop leaves you with either both effects or neither,
never one without the other.

Two designs both satisfy this (pick one -- see the README for the
tradeoff):

    (a) Idempotent dedup: record each event's unique `seq` in a dedup
        table under a PRIMARY KEY, `INSERT ... ON CONFLICT DO NOTHING`,
        and only apply the category-totals delta for rows that were
        actually newly inserted. Redelivery re-attempts the insert, loses
        the conflict, and the delta is skipped the second time.

    (b) Transactional offset storage: store the consumed Kafka offset per
        partition in your OWN Postgres table, in the SAME transaction as
        the category-totals update. On startup, seek each assigned
        partition to your stored offset (not the broker's committed
        offset) and resume from there. The aggregate delta and the offset
        advance commit atomically, so a crash before that transaction
        commits replays the same offset and reapplies the same delta
        exactly once; a crash after it commits never revisits that offset.

Either way, the whole "apply one event" operation must be one Postgres
transaction, and the Kafka offset commit must not run until that
transaction has durably committed.

Try it yourself before running the validator:

    S07_CRASH_AFTER=50000 uv run python src/consumer.py   # dies partway
    uv run python src/consumer.py                         # resumes, catches up
    uv run python src/consumer.py                         # rerun with nothing new: totals must not move
"""

import json
import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t04.price-updates"
GROUP_ID = "t04-consumer"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

CORE_DDL = """
CREATE TABLE IF NOT EXISTS core.t04_category_totals (
    category  TEXT PRIMARY KEY,
    cnt       BIGINT  NOT NULL DEFAULT 0,
    price_sum NUMERIC NOT NULL DEFAULT 0
)
"""


def ensure_core_table(conn) -> None:
    """Given plumbing. Creates the graded result table if it doesn't exist
    yet -- idempotent, safe to call on every run. Note: use explicit
    cursor + commit here (not `with conn:` -- on this psycopg build that
    context manager can close the connection on exit, not just end the
    transaction)."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
    cur.execute(CORE_DDL)
    conn.commit()


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S07_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it, bypassing anything -- Postgres commit or
    Kafka offset commit -- that hasn't happened yet. Call it once per
    message, AFTER your Postgres transaction has committed (so the crash
    window it simulates is "DB txn committed, Kafka offset commit not yet
    sent" -- the exact redelivery window your design must survive).
    """
    crash_after = os.environ.get("S07_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def on_assign(consumer, partitions) -> None:
    """Given plumbing, called by confluent-kafka when partitions are
    (re)assigned to this consumer.

    TODO (only needed for design (b), transactional offset storage): for
    each partition in `partitions`, look up the offset you last stored
    (transactionally, alongside a category-totals update) in your own
    ops.t04_* table, and call `p.offset = stored_offset + 1` before
    `consumer.assign(partitions)` so you resume exactly where your last
    committed Postgres transaction left off -- not from whatever the
    broker's committed offset happens to be.

    If you chose design (a) (idempotent dedup table), you don't need to
    touch this: leave it as a plain `consumer.assign(partitions)`. The
    broker's committed offset is a perfectly fine place to resume from,
    because your dedup table makes replaying a few already-seen messages
    (or even the full partition, if there's no committed offset yet) a
    no-op.
    """
    consumer.assign(partitions)


def main() -> None:
    from confluent_kafka import Consumer

    conn = pg_connect()
    ensure_core_table(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        # Short session timeout so a crashed member is evicted from the group
        # quickly -- a restarted consumer would otherwise wait out the default
        # 45s session timeout before the broker reassigns its partitions.
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    })
    consumer.subscribe([TOPIC], on_assign=on_assign)

    processed = 0
    idle_seconds = 0.0

    try:
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

            # TODO: apply this event's category-totals delta EXACTLY ONCE,
            # despite at-least-once redelivery across a crash.
            #
            # Whatever design you pick (see the module docstring above),
            # the shape is:
            #
            #   1. Open a Postgres transaction (a cursor + the connection's
            #      implicit transaction is enough -- don't use `with conn:`,
            #      see the note on ensure_core_table).
            #   2. Inside that ONE transaction: decide whether this event
            #      has already been applied (design a: try to insert its
            #      `seq` into a dedup table and check whether the insert
            #      actually happened; design b: this is always true because
            #      you're about to also persist the offset). If it has
            #      already been applied, skip the delta -- still commit
            #      (design b writes the offset either way; design a simply
            #      has nothing left to do).
            #   3. If not yet applied: upsert core.t04_category_totals for
            #      event["category"] -- cnt += 1, price_sum += event["price"]
            #      (INSERT ... ON CONFLICT (category) DO UPDATE, seeded at
            #      cnt=0/price_sum=0 if the category row doesn't exist yet).
            #      Design (b) also upserts this event's offset into your own
            #      ops.t04_* offsets table, in the SAME transaction.
            #   4. conn.commit() -- this is the atomic boundary. Everything
            #      above either lands together or (on a crash before this
            #      line) not at all; a redelivered message replays from
            #      step 1 with no partial effect left behind.
            #   5. THEN, and only then: processed += 1; _maybe_crash(processed);
            #      consumer.commit(msg). The Kafka offset commit is NOT part
            #      of the atomic unit -- it's fine for it to be lost or
            #      redone, because steps 1-4 are what make redelivery safe.
            raise NotImplementedError
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
