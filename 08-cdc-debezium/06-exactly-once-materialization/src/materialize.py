"""s08.t06 materializer -- exactly-once mart materialization from CDC.

CLI contract (what the validator relies on):

    uv run python src/materialize.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t06-materializer").
- Subscribes to topic TOPIC ("s08.t06.shop.offers").
- Maintains BOTH, in the MART database:
    (i)  replica.offers(offer_id, product_id, seller, price, currency,
         in_stock, updated_at) -- same columns as shop.offers, upserted from
         `after` on op in ('r','c','u'), deleted on op='d', skipped on a
         tombstone. This half alone is idempotent for free (task 03) -- an
         upsert and a DELETE are both safe to run twice.
    (ii) mart.t06_meta(applied_changes BIGINT) -- a single-row counter
         incremented by exactly 1 for every NON-tombstone change event
         (op in 'r','c','u','d') applied, no matter how many times Kafka
         redelivers that event. This half is NOT idempotent for free: a
         naive `applied_changes += 1` run twice for the same event silently
         over-counts.
- Honors env var S08_CRASH_AFTER: if set, the process hard-exits via
  os._exit(1) right after processing that many messages THIS RUN. See
  _maybe_crash below -- a TEST HOOK, already implemented, not something you
  write.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic) -- this is how the validator knows a run finished.
- Must be SAFE TO RUN REPEATEDLY, including resuming after a crash: the
  final state (both replica.offers AND mart.t06_meta.applied_changes) must
  be exactly what one uninterrupted run would have produced.

The problem in one sentence: task 03 already showed that an idempotent
upsert survives redelivery on its own -- re-applying the same `after` image
twice is a no-op. The moment you ALSO maintain a running aggregate next to
that upsert, idempotence of the upsert does not save you: a crash between
committing the mart write and committing the Kafka offset redelivers the
event, and `applied_changes += 1` run a second time for it is a silent
double-count. Exactly like 07/04, the fix is to make "apply this change" and
"remember I applied it" one atomic Postgres transaction, keyed on a per-event
identity, committed BEFORE the Kafka offset is ever touched.

Two designs both satisfy this (pick one -- see the README for the tradeoff):

    (a) Idempotent dedup: record each event's identity -- either the Kafka
        (partition, offset) pair (`msg.partition()`, `msg.offset()`) or the
        Debezium `source.lsn` field out of the decoded payload -- in your OWN
        ops.t06_* table under a PRIMARY KEY / UNIQUE constraint, via
        `INSERT ... ON CONFLICT DO NOTHING`. Apply the replica upsert/delete
        AND the mart.t06_meta increment only for rows that insert actually
        inserted, in the SAME transaction.

    (b) Transactional offset storage: store the consumed Kafka offset per
        partition in your OWN Postgres table, in the SAME transaction as the
        replica write and the mart.t06_meta increment. On startup, seek each
        assigned partition to your stored offset (via `on_assign`) instead of
        trusting the broker's committed offset.

Either way, one message's "apply" -- replica upsert-or-delete, plus (for a
non-tombstone event) the applied_changes increment, plus your dedup/offset
bookkeeping -- must be ONE Postgres transaction, and the Kafka offset commit
must not run until that transaction has durably committed.

Try it yourself before running the validator:

    S08_CRASH_AFTER=8000 uv run python src/materialize.py   # dies partway
    uv run python src/materialize.py                        # resumes, catches up
    uv run python src/materialize.py                        # rerun with nothing new: counter must not move
"""

import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import change_op, decode_value, kafka_bootstrap, mart_connect  # noqa: E402

TOPIC = "s08.t06.shop.offers"
GROUP_ID = "t06-materializer"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

REPLICA_DDL = """
CREATE TABLE IF NOT EXISTS replica.offers (
    offer_id   BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    seller     TEXT NOT NULL,
    price      NUMERIC NOT NULL,
    currency   TEXT NOT NULL,
    in_stock   BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ
)
"""

META_DDL = """
CREATE TABLE IF NOT EXISTS mart.t06_meta (
    id               SMALLINT PRIMARY KEY,
    applied_changes  BIGINT NOT NULL DEFAULT 0
)
"""


def ensure_mart_tables(conn) -> None:
    """Given plumbing. Creates the graded tables if they don't exist yet, and
    seeds the single meta row -- idempotent, safe to call on every run. Note:
    use explicit cursor + commit here (not `with conn:` -- on this psycopg
    build that context manager can close the connection on exit, not just
    end the transaction)."""
    cur = conn.cursor()
    cur.execute(REPLICA_DDL)
    cur.execute(META_DDL)
    cur.execute("INSERT INTO mart.t06_meta (id, applied_changes) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
    conn.commit()


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S08_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it, bypassing anything -- Postgres commit or
    Kafka offset commit -- that hasn't happened yet. Call it once per
    message, AFTER your Postgres transaction has committed (so the crash
    window it simulates is "mart txn committed, Kafka offset commit not yet
    sent" -- the exact redelivery window your design must survive).
    """
    crash_after = os.environ.get("S08_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def on_assign(consumer, partitions) -> None:
    """Given plumbing, called by confluent-kafka when partitions are
    (re)assigned to this consumer.

    TODO (only needed for design (b), transactional offset storage): for
    each partition in `partitions`, look up the offset you last stored
    (transactionally, alongside a replica write and a meta increment) in
    your own ops.t06_* table, and set `p.offset = stored_offset + 1` before
    `consumer.assign(partitions)` so you resume exactly where your last
    committed Postgres transaction left off -- not from whatever the
    broker's committed offset happens to be.

    If you chose design (a) (idempotent dedup table keyed on event
    identity), you don't need to touch this: leave it as a plain
    `consumer.assign(partitions)`. Your dedup table makes replaying
    already-seen events a no-op regardless of where the broker resumes from.
    """
    consumer.assign(partitions)


def apply_change(conn, op, before, after, msg, payload) -> None:
    """Apply one decoded change event to the mart EXACTLY ONCE, despite
    at-least-once Kafka redelivery. `op` is one of 'r', 'c', 'u', 'd' (never
    None -- tombstones are filtered out by the caller before this is
    invoked). `msg` is the raw confluent_kafka Message (for `.partition()`
    / `.offset()`); `payload` is the decoded Debezium payload dict (for
    `payload["source"]["lsn"]`), in case your dedup key is the LSN instead.

    TODO: implement. Shape (one Postgres transaction):
      1. Decide whether this event's identity has already been applied
         (design a: INSERT its identity into your own ops.t06_* table under
         a PRIMARY KEY/UNIQUE constraint via ON CONFLICT DO NOTHING, check
         whether the insert actually happened -- e.g. via cur.rowcount or
         `... RETURNING` + fetchone(); design b: this is always "not yet",
         because you are about to persist the offset in this same txn
         regardless).
      2. If (and only if) not already applied:
         - op in ('r', 'c', 'u'): upsert replica.offers from `after`,
           keyed on offer_id (INSERT ... ON CONFLICT (offer_id) DO UPDATE).
         - op == 'd': DELETE FROM replica.offers WHERE offer_id = before's
           offer_id.
         - UPDATE mart.t06_meta SET applied_changes = applied_changes + 1
           WHERE id = 1.
         (Design b also upserts this event's offset into your own
         ops.t06_* offsets table here, in the SAME transaction.)
      3. If already applied: skip step 2 entirely -- still commit (an empty
         no-op commit is fine, it just has to happen so the loop moves on).
      4. conn.commit() -- the atomic boundary. Everything in step 2 either
         lands together or (on a crash before this line) not at all; a
         redelivered event replays from step 1 with no partial effect left
         behind, and in particular applied_changes never moves twice for
         the same event.
    """
    raise NotImplementedError


def main() -> None:
    from confluent_kafka import Consumer

    conn = mart_connect()
    ensure_mart_tables(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
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

            payload = decode_value(msg.value())
            op, before, after = change_op(payload)
            if op is not None:
                apply_change(conn, op, before, after, msg, payload)

            processed += 1
            _maybe_crash(processed)
            consumer.commit(msg)
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
