"""s08.cap capstone materializer -- converges mart replica.offers with source
shop.offers, exactly once, across crashes and an additive schema change.

CLI contract (what the validators rely on):

    uv run python src/pipeline.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID ("cap-materializer").
- Subscribes to TOPIC ("s08.cap.shop.offers"). Validators register this
  task's connector with decimal.handling.mode=double, so after["price"] /
  before["price"] arrive as plain JSON numbers, not base64 Decimal bytes.
- For every event, exactly once, in ONE mart Postgres transaction:
    1. Dedup on (partition, offset) via ops.cap_seen -- INSERT ... ON
       CONFLICT DO NOTHING. Only apply the effects below when that insert
       actually inserted a new row; a redelivered (partition, offset) is a
       no-op transaction that still commits cleanly.
    2. Upsert/delete replica.offers from the decoded event (task 03's
       upsert-or-delete shape, generalized with a nullable discount_pct
       column that may or may not be present on a given event -- see
       "Schema evolution" below).
    3. mart.cap_meta(applied_changes) += 1 for that one event.
  Commit once. Tombstones (decoded payload is None) are skipped before any
  of this runs -- they carry no row state, only the dedup-relevant delete
  already happened on the preceding 'd' event.
- Honors S08_CRASH_AFTER exactly like modules 07/08's other crash hooks:
  _maybe_crash hard-exits the instant this run's processed-count reaches
  it. Called AFTER the mart transaction commits and BEFORE the Kafka offset
  commit -- that gap is the redelivery window your dedup design is graded
  on surviving.
- Exits 0 once idle for IDLE_EXIT_SECONDS (caught up with the topic).
- Resumable: safe to run repeatedly, including after a crash mid-run or a
  prior run that only got partway through the topic.

Why (partition, offset) and not source LSN
--------------------------------------------
Debezium's `source` block on every payload carries the change's LSN, and
that would work as a dedup key too -- but (partition, offset) is already
exactly what Kafka uses to decide "have I seen this message before" for
its OWN offset bookkeeping, so reusing it here means one mental model for
both layers, and it is available on every message without reaching into
`payload["source"]["lsn"]`. Either key is a valid answer; pick one and be
consistent -- do not dedup on some events by offset and others by LSN.

Schema evolution (discount_pct)
---------------------------------
CP2 runs `ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2)` on
the SOURCE mid-stream, live, with this connector still running. Debezium
picks up the new column on the next change event without a connector
restart (pgoutput sends an updated relation description); events published
BEFORE the ALTER simply have no "discount_pct" key in `after` at all.
replica.offers must have a discount_pct column from the START (this
task's ensure_tables creates it unconditionally, nullable) so there is
nothing to migrate on the mart side -- the only thing your apply code must
do is read the field defensively (`after.get("discount_pct")`, not
`after["discount_pct"]`), so pre-ALTER events don't KeyError and simply
write NULL.

Why the crash window can't double-apply
------------------------------------------
Same shape as module 07's capstone: _maybe_crash fires after the mart
transaction (dedup insert + replica upsert/delete + cap_meta increment)
has committed, before the Kafka offset commit. A crash there means the
same (partition, offset) is redelivered on restart (or to whichever
instance ends up owning that partition). ops.cap_seen already has that
key, so the dedup insert loses its ON CONFLICT race, every downstream
effect is skipped, and the transaction commits as a no-op. Kafka's offset
commit is deliberately outside the atomic unit for exactly this reason --
it is fine for it to be lost, because the mart alone decides what is safe
to (re)apply.
"""

import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import change_op, decode_value, kafka_bootstrap, mart_connect  # noqa: E402

TOPIC = "s08.cap.shop.offers"
GROUP_ID = "cap-materializer"
IDLE_EXIT_SECONDS = 15.0
POLL_TIMEOUT_SECONDS = 1.0

REPLICA_DDL = """
CREATE TABLE IF NOT EXISTS replica.offers (
    offer_id     BIGINT PRIMARY KEY,
    product_id   BIGINT NOT NULL,
    seller       TEXT NOT NULL,
    price        NUMERIC NOT NULL,
    currency     TEXT NOT NULL,
    in_stock     BOOLEAN NOT NULL,
    discount_pct NUMERIC(5, 2),
    updated_at   TIMESTAMPTZ
)
"""

CAP_META_DDL = """
CREATE TABLE IF NOT EXISTS mart.cap_meta (
    id              INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    applied_changes BIGINT NOT NULL DEFAULT 0
)
"""

OPS_SEEN_DDL = """
CREATE TABLE IF NOT EXISTS ops.cap_seen (
    partition INT NOT NULL,
    "offset"  BIGINT NOT NULL,
    PRIMARY KEY (partition, "offset")
)
"""


def ensure_tables(conn) -> None:
    """Given plumbing. Creates every table this pipeline maintains, and
    seeds mart.cap_meta's single row, if they don't exist yet -- idempotent,
    safe to call on every run. Note the psycopg gotcha from other module
    08/07 tasks: use an explicit cursor + conn.commit(), not `with conn:`
    (that context manager can close the connection on __exit__ on this
    build, not just end the transaction)."""
    cur = conn.cursor()
    cur.execute(REPLICA_DDL)
    cur.execute(CAP_META_DDL)
    cur.execute(OPS_SEEN_DDL)
    cur.execute("INSERT INTO mart.cap_meta (id, applied_changes) VALUES (1, 0) ON CONFLICT DO NOTHING")
    conn.commit()


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S08_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it. Call once per message, AFTER the mart
    transaction for that message has committed and BEFORE the Kafka offset
    commit -- that is the exact crash window CP2 grades your dedup design
    against.
    """
    crash_after = os.environ.get("S08_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def apply_event_exactly_once(conn, partition: int, offset: int, op: str, before, after) -> None:
    """The crux of this task. Apply one decoded change event to the mart,
    exactly once, in a single transaction gated by (partition, offset).

    `op` is one of 'r', 'c', 'u', 'd' (never None -- tombstones are already
    filtered out by the caller). `before`/`after` are the decoded Debezium
    images (see harness.common.change_op).

    TODO: implement.

    Shape:
      1. cur = conn.cursor()
      2. INSERT INTO ops.cap_seen (partition, "offset") VALUES (%s, %s)
         ON CONFLICT DO NOTHING. Check whether the insert actually
         happened (cur.rowcount == 1, or RETURNING + fetchone()).
      3. Only if it happened (this (partition, offset) has never been
         applied before), in the SAME transaction:
         a. op in ('r', 'c', 'u'): upsert replica.offers from `after`,
            keyed on offer_id -- same upsert-or-delete shape as task 03,
            plus discount_pct = after.get("discount_pct") (defensive: the
            key may be entirely absent on events published before CP2's
            mid-stream ALTER TABLE).
            op == 'd': DELETE FROM replica.offers WHERE offer_id =
            before's offer_id.
         b. UPDATE mart.cap_meta SET applied_changes = applied_changes + 1
            WHERE id = 1.
         If step 2's insert lost the conflict (already applied), skip 3a/3b
         entirely -- still commit (an empty no-op).
      4. conn.commit() -- once. Everything above lands together, or (crash
         before this line) not at all.

    The caller does step 5 (processed += 1; _maybe_crash(processed);
    consumer.commit(msg)) AFTER this function returns.
    """
    raise NotImplementedError


def main() -> None:
    from confluent_kafka import Consumer

    conn = mart_connect()
    ensure_tables(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    })
    consumer.subscribe([TOPIC])

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
                apply_event_exactly_once(conn, msg.partition(), msg.offset(), op, before, after)

            processed += 1
            _maybe_crash(processed)
            consumer.commit(msg)
    finally:
        consumer.close()
        conn.close()

    print(f"caught up: processed {processed} messages this run")


if __name__ == "__main__":
    main()
