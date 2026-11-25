"""s08.t05 replica lag monitor -- one snapshot per invocation.

CLI contract (what the validator relies on):

    uv run python src/monitor.py

Behavior contract:
- Takes exactly ONE snapshot of replica lag and exits 0. It is NOT a poll
  loop -- run it again later to see how lag changed.
- Measures lag two different ways, from two different systems:
    1. CONSUMER lag on Kafka: how many change events are sitting on
       TOPIC that the materializer consumer group (GROUP_ID) has not yet
       committed. This is "how far behind is the thing reading the topic."
    2. Replication SLOT lag on the SOURCE: how many bytes of WAL Postgres
       is retaining for SLOT_NAME because the slot hasn't confirmed
       flushing past them yet. This is "how far behind is Debezium itself
       in draining the write-ahead log," a question a RabbitMQ queue has
       no equivalent of -- a queue doesn't pin disk-resident WAL on a
       producer's behalf.
  Both numbers get written into one row of ops.t05_lag_snapshots, plus a
  boolean alert decided from the consumer-lag number.
- Safe to run repeatedly: each run INSERTs a new row (snapshot_id is
  BIGSERIAL), it never overwrites or deletes a prior snapshot.

The one thing you must implement, in main() below:

1. Consumer lag: total (not per-partition) unconsumed-event count for
   GROUP_ID against TOPIC. harness.common has a helper that already does
   exactly this arithmetic (high watermark minus committed offset, summed
   across partitions) -- this task does not ask you to reimplement it, use
   it directly.

2. Slot lag bytes: how much WAL the source is retaining for SLOT_NAME,
   defined as the gap between the source's current WAL position and the
   slot's own confirmed_flush_lsn -- i.e. how far the slot's consumer
   (Debezium) is behind the latest write, in bytes. You have two pieces on
   the SOURCE connection to build this from:
     - harness.common.source_current_lsn(conn) -- the source's current WAL
       LSN right now.
     - harness.common.replication_slots(conn) -- one row per replication
       slot, including confirmed_flush_lsn; find the row for SLOT_NAME.
   Note replication_slots() already computes its own "lag_bytes" column,
   but it measures the gap against restart_lsn (the oldest WAL the slot
   still pins for a possible restart), not confirmed_flush_lsn (how far
   the slot has actually confirmed processing). Those two LSNs usually sit
   close together but answer different questions -- for this task you want
   the confirmed_flush_lsn-based figure, which means computing it
   yourself: Postgres exposes the byte-distance between two LSNs via the
   pg_wal_lsn_diff(lsn1, lsn2) SQL function, callable from a query you run
   over the SOURCE connection.

3. Decide alert = consumer_lag > lag_threshold() (strictly greater; a
   snapshot sitting exactly at the threshold does not alert).

4. INSERT one row into ops.t05_lag_snapshots (consumer_lag, slot_lag_bytes,
   alert) and commit. Do the read + insert + commit as one unit of work
   per snapshot, same discipline as this module's other ops tables: a
   snapshot is either fully written or not written at all.

psycopg gotcha on this build (3.x): do not use `with conn:` as a
transaction context manager -- it can close the connection on __exit__,
not just end the transaction. Use an explicit cursor + conn.commit().
"""

import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    consumer_lag,
    mart_connect,
    replication_slots,
    source_connect,
    source_current_lsn,
)

TOPIC = "s08.t05.shop.offers"
GROUP_ID = "t05-materializer"
SLOT_NAME = "s08_t05_slot"
DEFAULT_LAG_THRESHOLD = 1000

OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops.t05_lag_snapshots (
    snapshot_id    BIGSERIAL PRIMARY KEY,
    taken_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    consumer_lag   BIGINT NOT NULL,
    slot_lag_bytes BIGINT NOT NULL,
    alert          BOOLEAN NOT NULL
);
"""


def ensure_ops_table(conn) -> None:
    """Given plumbing. Creates the table this task is graded on, if it
    doesn't exist yet -- idempotent, safe to call on every run."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(OPS_DDL)
    conn.commit()


def lag_threshold() -> int:
    return int(os.environ.get("S08_LAG_THRESHOLD", str(DEFAULT_LAG_THRESHOLD)))


def main() -> None:
    mart = mart_connect()
    ensure_ops_table(mart)

    source = source_connect()
    try:
        # TODO: implement the one snapshot this task is graded on.
        #
        #   1. total_consumer_lag = consumer_lag(GROUP_ID, TOPIC)
        #   2. slot_lag_bytes = <bytes between the source's current WAL LSN
        #      and slot SLOT_NAME's confirmed_flush_lsn> -- see the module
        #      docstring above for which two helpers to combine and which
        #      SQL function does the byte arithmetic.
        #   3. alert = total_consumer_lag > lag_threshold()
        #   4. INSERT one row into ops.t05_lag_snapshots
        #      (consumer_lag, slot_lag_bytes, alert), then mart.commit().
        raise NotImplementedError
    finally:
        source.close()

    mart.close()


if __name__ == "__main__":
    main()
