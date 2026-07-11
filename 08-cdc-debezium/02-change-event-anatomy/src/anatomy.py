"""s08.t02 consumer -- change-event anatomy.

CLI contract (what the validator relies on):

    uv run python src/anatomy.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t02-anatomy").
- Subscribes to topic TOPIC ("s08.t02.shop.offers").
- Every message value is a Debezium JsonConverter envelope
  ({"schema": ..., "payload": ...}); harness.common.decode_value() unwraps
  it to the payload dict, and harness.common.change_op(payload) returns
  (op, before, after) where op is one of:
    "r" -- read (snapshot row, emitted once per existing source row)
    "c" -- create (insert)
    "u" -- update
    "d" -- delete
  or (None, None, None) for a tombstone record (published right after a
  delete, when tombstones.on.delete=true -- the connector default). A
  tombstone carries no payload; skip it.
- Maintains ops.t02_change_summary(op, n): across the WHOLE run (snapshot
  "r" events plus streaming "c"/"u"/"d" events), n is the exact count of
  events seen for that op.
- Maintains ops.t02_decoded_prices(offer_id, price): for every "u" event
  only, the DECODED after-image price, keyed by offer_id -- last value wins
  if the same offer is updated more than once in this run.
- The gotcha this task is built around: under the connector's default
  decimal.handling.mode (precise, left unset in the config the validator
  registers), a NUMERIC column's value is NOT a plain JSON number. It's the
  Kafka Connect Decimal logical type: a base64 string encoding the
  two's-complement big-endian bytes of the UNSCALED integer. shop.offers.price
  is NUMERIC(12, 2), so its scale is fixed at 2 -- PRICE_SCALE below. See
  decode_decimal()'s docstring for the exact algorithm to implement.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic, including the full snapshot).
- Must be SAFE TO RUN REPEATEDLY: TRUNCATEs both graded tables at startup
  (see ensure_tables), then rebuilds them from a full replay of the topic
  from the beginning.

Try it yourself before running the validator:

    uv run python src/anatomy.py
"""

import base64  # noqa: F401  -- you'll want this in decode_decimal
import sys
from decimal import Decimal
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import change_op, decode_value, kafka_bootstrap, mart_connect  # noqa: E402

TOPIC = "s08.t02.shop.offers"
GROUP_ID = "t02-anatomy"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

# shop.offers.price is NUMERIC(12, 2) -- fixed scale, per the module's
# documented source schema.
PRICE_SCALE = 2

SUMMARY_DDL = """
CREATE TABLE IF NOT EXISTS ops.t02_change_summary (
    op TEXT PRIMARY KEY,
    n  BIGINT NOT NULL DEFAULT 0
)
"""

PRICES_DDL = """
CREATE TABLE IF NOT EXISTS ops.t02_decoded_prices (
    offer_id BIGINT PRIMARY KEY,
    price    NUMERIC(12, 2) NOT NULL
)
"""


def ensure_tables(conn) -> None:
    """Given plumbing. Creates both graded tables if they don't exist yet,
    then truncates them -- this consumer always rebuilds its output from a
    full replay of the topic, so stale rows from a previous run must not
    survive."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(SUMMARY_DDL)
    cur.execute(PRICES_DDL)
    cur.execute("TRUNCATE ops.t02_change_summary")
    cur.execute("TRUNCATE ops.t02_decoded_prices")
    conn.commit()


def decode_decimal(encoded: str, scale: int) -> Decimal:
    """TODO: crack the Kafka Connect Decimal logical type.

    `encoded` is the raw string found at after["price"] in a decoded
    payload -- e.g. "GSc=" -- NOT a number, a base64 string. Kafka Connect's
    Decimal logical type encodes a NUMERIC value as the two's-complement
    big-endian bytes of its UNSCALED integer (the integer you'd get by
    multiplying the real value by 10**scale). `scale` is PRICE_SCALE for
    this column (NUMERIC(12, 2)).

    Return the decoded value as a Decimal, not a float -- the validator
    checks for an EXACT match against the source's NUMERIC(12,2) price, and
    a binary float cannot represent every two-decimal value exactly.
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
                continue  # tombstone -- nothing to tally or decode

            # TODO, for EVERY event reaching this point (snapshot "r"
            # events included):
            #   (i)  tally this event's op into ops.t02_change_summary --
            #        upsert a single row per op: n=1 the first time an op
            #        is seen, incremented by 1 on every later sighting.
            #   (ii) if op == "u": decode after["price"] via
            #        decode_decimal(after["price"], PRICE_SCALE) and
            #        upsert (offer_id, price) into ops.t02_decoded_prices,
            #        keyed by after["offer_id"] (ON CONFLICT DO UPDATE, so
            #        an offer updated more than once this run ends up
            #        holding its latest decoded price).
            # Commit once per message.
            raise NotImplementedError
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
