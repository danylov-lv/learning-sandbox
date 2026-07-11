"""s08.t04 materializer -- a consumer that survives an additive schema
change on the source mid-stream.

CLI contract (what the validator relies on):

    uv run python src/materialize.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t04-materializer").
- Subscribes to topic TOPIC ("s08.t04.shop.offers").
- Maintains mart table replica.offers(offer_id, product_id, seller, price,
  currency, in_stock, discount_pct): op='r'/'c'/'u' upserts the after-image
  keyed by offer_id; op='d' deletes the row keyed by before's offer_id; a
  tombstone (decoded payload is None) is a no-op -- skip it.
- discount_pct is nullable and is NOT part of the source schema when this
  table is first created. It becomes real partway through the module 08
  task-04 validator run, when the source does:

      ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2)

  This is an ADDITIVE change: pgoutput and Debezium propagate the new
  column automatically, with no special DDL event a consumer has to react
  to. Every after-image published BEFORE the ALTER simply does not have a
  "discount_pct" key at all; every after-image published AFTER it does.
  Your apply logic must handle both shapes of the SAME topic, in the SAME
  run, without crashing or needing to know in advance which one it's
  looking at.
- Exits 0 once idle for IDLE_EXIT_SECONDS (caught up with the topic).
- Safe to run repeatedly / resume from any point: every change event
  carries the full current row (not a delta), so upsert-by-primary-key and
  delete-by-primary-key are both naturally idempotent -- rerunning against
  already-applied events, or restarting mid-stream, cannot corrupt
  replica.offers.

The crux of this task is `apply_change` below. The connector this
validator registers sets `decimal.handling.mode=double`, so NUMERIC
columns (price, discount_pct) arrive as plain JSON numbers -- no base64
decoding needed here (that's task 02's concern, not this one).

Try it by hand before trusting the validator:

    uv run python src/materialize.py   # converges the pre-DDL snapshot/stream
    # ... source team runs the ALTER TABLE ADD COLUMN, more events land ...
    uv run python src/materialize.py   # must not crash; converges again
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import change_op, decode_value, kafka_bootstrap, mart_connect  # noqa: E402

TOPIC = "s08.t04.shop.offers"
GROUP_ID = "t04-materializer"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

REPLICA_DDL = """
CREATE TABLE IF NOT EXISTS replica.offers (
    offer_id     BIGINT PRIMARY KEY,
    product_id   BIGINT,
    seller       TEXT,
    price        NUMERIC(12, 2),
    currency     TEXT,
    in_stock     BOOLEAN,
    discount_pct NUMERIC(5, 2)
)
"""


def ensure_replica_table(conn) -> None:
    """Given plumbing. Creates replica.offers if it doesn't exist yet --
    idempotent, safe to call on every run. Note discount_pct is created
    UP FRONT, before the source ever has the column: the replica schema is
    made forward-compatible ahead of the source's migration, which is why
    the apply logic below never needs to ALTER replica.offers itself."""
    cur = conn.cursor()
    cur.execute(REPLICA_DDL)
    conn.commit()


def apply_change(conn, op, before, after) -> None:
    """TODO: apply ONE decoded Debezium change event to replica.offers,
    defensively across the ADD COLUMN discount_pct boundary.

    `op` is 'r', 'c', 'u', or 'd' (see harness.common.change_op). `before`
    and `after` are dicts or None, exactly as change_op() returns them.

    For 'r' / 'c' / 'u': upsert the row keyed by after["offer_id"] with
    product_id, seller, price, currency, in_stock, and discount_pct from
    `after`. Read discount_pct via `after.get("discount_pct")` -- this
    returns None whenever the key is simply absent from this event's
    after-image, which is true for EVERY event produced before the
    source's ALTER TABLE ... ADD COLUMN, and would also be true for any
    other column a future migration adds that this code doesn't know
    about yet. Do NOT write `after["discount_pct"]` (KeyErrors on any
    after-image that predates the column) and do NOT build a fixed
    positional tuple of "the columns I expect" -- that pattern silently
    breaks (or crashes) the instant the source's shape changes under you.
    Use ON CONFLICT (offer_id) DO UPDATE so redelivery of the same
    after-image is a no-op change, not a duplicate row.

    For 'd': delete the row for before["offer_id"] (before is a full
    pre-image here because shop.offers has REPLICA IDENTITY FULL) -- use
    the same defensive .get() discipline if you read any other field off
    `before`, and make the delete idempotent (deleting an already-deleted
    offer_id must not raise).
    """
    raise NotImplementedError


def main() -> None:
    from confluent_kafka import Consumer

    conn = mart_connect()
    ensure_replica_table(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([TOPIC])

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
            if op is None:
                # Tombstone -- published right after a delete's own 'd'
                # event when tombstones.on.delete=true. The 'd' event
                # already did the work; this is a no-op, just advance past it.
                consumer.commit(msg)
                continue

            apply_change(conn, op, before, after)
            consumer.commit(msg)
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
