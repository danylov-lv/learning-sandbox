"""s08.t03 materializer -- apply shop.offers change events to a mart replica.

CLI contract (what the validator relies on):

    uv run python src/materialize.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t03-materializer").
- Subscribes to topic TOPIC ("s08.t03.shop.offers").
- Maintains replica.offers(offer_id, product_id, seller, price, currency,
  in_stock, updated_at) in the MART database -- same columns as the
  source's shop.offers -- so that after consuming the whole topic,
  replica.offers is an exact copy of shop.offers as it stood on the
  source at the time you stopped consuming.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic) -- this is how the validator knows a run finished.
- Must be SAFE TO RUN REPEATEDLY: a fresh run against an empty
  replica.offers, or a resumed run after a previous run already applied
  part of the stream, must converge on the same table a single
  uninterrupted run would have produced. Kafka is at-least-once -- the
  same event can arrive twice.

Event shapes you'll see on this topic (via harness.common.change_op):
    op='r'  snapshot row,  before=None,        after=<full row>
    op='c'  insert,        before=None,        after=<full row>
    op='u'  update,        before=<old row>,   after=<new row>
    op='d'  delete,        before=<old row>,   after=None
    tombstone: decoded payload is None (already filtered out below,
               before your code runs)

Note on prices: this task's connector is registered by the validator with
decimal.handling.mode=double, so after["price"] / before["price"] here are
plain JSON numbers already -- NOT the base64-encoded Kafka Connect Decimal
bytes from task 02. Decoding that encoding by hand was task 02's exercise;
here you can use the number as-is.

The problem in one sentence: three event shapes (snapshot row, insert,
update, delete) collapse into two things you do to replica.offers (upsert,
delete), and the apply must be idempotent -- applying the same event a
second time (redelivery, or you rerunning this script) must never change
the outcome.

    op in ('r', 'c', 'u'): upsert replica.offers from `after`, keyed on
        offer_id (INSERT ... ON CONFLICT (offer_id) DO UPDATE). A snapshot
        row, an insert, and an update all mean the same thing to the
        replica: "this offer_id now looks like `after`."
    op == 'd': DELETE FROM replica.offers WHERE offer_id = before's
        offer_id. There is no `after` on a delete -- the key comes from
        `before`.

Try it yourself before running the validator:

    uv run python src/materialize.py   # first run: fills from the snapshot
    uv run python src/materialize.py   # rerun with nothing new: idle-exits, table unchanged
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import change_op, decode_value, kafka_bootstrap, mart_connect  # noqa: E402

TOPIC = "s08.t03.shop.offers"
GROUP_ID = "t03-materializer"
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


def ensure_replica_table(conn) -> None:
    """Given plumbing. Creates the graded result table if it doesn't exist
    yet -- idempotent, safe to call on every run. Note: use explicit
    cursor + commit here (not `with conn:` -- on this psycopg build that
    context manager can close the connection on exit, not just end the
    transaction)."""
    cur = conn.cursor()
    cur.execute(REPLICA_DDL)
    conn.commit()


def apply_change(conn, op, before, after) -> None:
    """Apply one decoded change event to replica.offers. `op` is one of
    'r', 'c', 'u', 'd' (never None -- tombstones are filtered out by the
    caller before this is invoked).

    TODO: implement.

    Shape:
      - op in ('r', 'c', 'u'): upsert from `after` -- INSERT the row keyed
        on offer_id, ON CONFLICT (offer_id) DO UPDATE every other column
        from the same values. This must be safe to run twice for the same
        `after` image (redelivery, or a rerun) -- an upsert already is,
        as long as you don't add extra state elsewhere that isn't.
      - op == 'd': DELETE FROM replica.offers WHERE offer_id = <before's
        offer_id>. DELETE of a row that's already gone is a no-op in SQL,
        not an error -- that's what makes this safe to run twice too.
      - Commit once per event (one Postgres transaction each is fine here
        -- there's no cross-system atomicity requirement in this task,
        unlike 07/04's exactly-once aggregation).
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
            if op is not None:
                apply_change(conn, op, before, after)

            consumer.commit(msg)
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
