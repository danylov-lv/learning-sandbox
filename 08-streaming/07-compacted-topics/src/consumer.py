"""s07.t07 consumer -- materialize latest-price-per-product from a compacted
topic, last-write-wins by PUBLISH ORDER (seq), not by event_ts.

CLI contract (what the validator relies on):

    uv run python src/consumer.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t07-consumer").
- Subscribes to topic TOPIC ("s07.t07.latest-price") FROM THE BEGINNING.
- For each message, upserts the decoded event into
  core.t07_latest_price(product_id PRIMARY KEY, price, currency, in_stock,
  event_ts, seq) -- see ensure_table() below for the exact DDL, already
  written for you.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic). Safe to rerun: rerunning after it already caught up should
  do nothing but confirm there's nothing left to read.

Why this is NOT the same problem as task 05 (windowed aggregation):
task 05 needed the correct event-TIME bucket, so a late event (one whose
event_ts is earlier than its neighbors but which was PUBLISHED later, at a
higher seq) belongs in the window its event_ts says, no matter when it
arrived. This task wants the opposite: "what does this product's price look
like right now, to whoever's serving traffic" -- and that answer is
determined by the LAST WRITE, i.e. the highest seq this consumer has seen for
that product_id, regardless of what event_ts that write happens to carry. A
late event can have an event_ts earlier than the row currently in the table
and still be the correct new value, because it was published after. Get this
backwards -- keep whichever row has the larger event_ts -- and you'll get a
handful of products wrong: exactly the late ones.

Try it yourself before running the validator:

    uv run python src/setup_topic.py             # create the compacted topic
    # produce some events at it yourself, or just run the validator, which
    # produces the full corpus into its own copy of the topic
    uv run python src/consumer.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t07.latest-price"
GROUP_ID = "t07-consumer"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

DDL = """
CREATE TABLE IF NOT EXISTS core.t07_latest_price (
    product_id INT PRIMARY KEY,
    price NUMERIC NOT NULL,
    currency TEXT NOT NULL,
    in_stock BOOLEAN NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    seq BIGINT NOT NULL
)
"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def upsert_latest(conn, event: dict) -> None:
    """Insert or update this product's row, but ONLY if this event's seq is
    newer than whatever is already stored -- otherwise an out-of-order
    redelivery or a late event with a lower seq could clobber a newer row.

    TODO: write the INSERT ... ON CONFLICT (product_id) DO UPDATE ... here.
    Guard the DO UPDATE with a WHERE clause comparing EXCLUDED.seq against
    the existing row's seq (core.t07_latest_price.seq) so it only fires when
    the incoming event is actually the later write. Without that guard, a
    consumer that (re)reads the topic out of seq order -- or gets rerun --
    can overwrite a correct row with a stale one.

    Columns to write: product_id, price, currency, in_stock, event_ts, seq.
    Remember to conn.commit() (this psycopg version's `with conn:` context
    manager can close the connection on exit -- don't rely on it here).
    """
    raise NotImplementedError


def main() -> None:
    from confluent_kafka import Consumer

    conn = pg_connect()
    ensure_table(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([TOPIC])

    processed = 0
    idle_seconds = 0.0

    try:
        while idle_seconds < IDLE_EXIT_SECONDS:
            # TODO: implement the consume loop.
            #
            # Each iteration:
            #   1. msg = consumer.poll(POLL_TIMEOUT_SECONDS)
            #   2. If msg is None: bump idle_seconds by POLL_TIMEOUT_SECONDS,
            #      continue.
            #   3. If msg.error(): reset idle_seconds to 0, continue (topic
            #      is still alive, just this poll came back an error).
            #   4. Otherwise: reset idle_seconds to 0, decode msg.value()
            #      with json.loads() into an event dict, call
            #      upsert_latest(conn, event), consumer.commit(msg), and
            #      increment processed.
            raise NotImplementedError
    finally:
        consumer.close()
        conn.close()

    print(f"caught up: processed {processed} messages this run")


if __name__ == "__main__":
    main()
