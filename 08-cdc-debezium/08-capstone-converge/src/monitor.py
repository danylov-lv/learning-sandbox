"""s08.cap lag monitor -- one lag snapshot for the capstone pipeline, both
consumer-group lag (Kafka side) and replication-slot lag (Postgres source
side), with a simple alert flag.

CLI contract (what the validators rely on):

    uv run python src/monitor.py

Behavior contract:
- Takes exactly ONE snapshot for GROUP_ID ("cap-materializer") /
  TOPIC ("s08.cap.shop.offers") / SLOT_NAME ("s08_cap_slot"), then exits 0.
  Does not consume any messages from TOPIC -- only broker metadata
  (watermarks, committed offsets) plus one query against the SOURCE's
  pg_replication_slots.
- Writes one row PER PARTITION into ops.cap_lag_snapshots for this
  snapshot, each row carrying the same slot_lag_bytes and alert values
  (the slot itself has no per-partition breakdown -- it is one replication
  connection for the whole table).
- Safe to run repeatedly: each run appends a new snapshot_id, never
  overwrites or deletes a prior one.

Two lag signals, and why both matter
--------------------------------------
Consumer lag (high watermark - committed offset, per partition) tells you
how far this pipeline is behind what Kafka already has. Slot lag in bytes
(pg_current_wal_lsn() - restart_lsn, from harness.common.replication_slots)
tells you how far the Debezium connector itself is behind the SOURCE's
write-ahead log -- a stalled or crashed connector can pin WAL and grow
WITHOUT the consumer lag ever moving, because there is nothing new in
Kafka for the consumer to be behind on. A healthy pipeline needs both
numbers, not just one.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    committed_offsets,
    end_offsets,
    mart_connect,
    replication_slots,
    source_connect,
)

TOPIC = "s08.cap.shop.offers"
GROUP_ID = "cap-materializer"
SLOT_NAME = "s08_cap_slot"

ALERT_CONSUMER_LAG_THRESHOLD = 5000
ALERT_SLOT_LAG_BYTES_THRESHOLD = 5_000_000

OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops.cap_lag_snapshots (
    snapshot_id      BIGINT NOT NULL,
    topic            TEXT   NOT NULL,
    group_id         TEXT   NOT NULL,
    partition        INT    NOT NULL,
    high_watermark   BIGINT NOT NULL,
    committed_offset BIGINT NOT NULL,
    consumer_lag     BIGINT NOT NULL,
    slot_lag_bytes   BIGINT,
    alert            BOOLEAN NOT NULL,
    captured_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def ensure_ops_table(conn) -> None:
    """Given plumbing. Creates the table this task is graded on, if it
    doesn't exist yet -- idempotent, safe to call on every run."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(OPS_DDL)
    conn.commit()


def next_snapshot_id(conn) -> int:
    """Given plumbing. Each run appends a new snapshot rather than
    overwriting a previous one."""
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(snapshot_id), 0) + 1 FROM ops.cap_lag_snapshots")
    return cur.fetchone()[0]


def fetch_slot_lag_bytes() -> int | None:
    """Given plumbing. Opens its own short-lived SOURCE connection (this
    task's mart-side monitor otherwise never touches the source) and reads
    the current lag, in bytes, of the connector's replication slot. Returns
    None if the slot does not exist (e.g. connector not registered yet)."""
    conn = source_connect()
    try:
        for slot in replication_slots(conn):
            if slot["slot_name"] == SLOT_NAME:
                return int(slot["lag_bytes"])
        return None
    finally:
        conn.close()


def record_snapshot(conn) -> int:
    """The one thing to implement in this task.

    TODO: implement.

    Shape:
      1. high = end_offsets(TOPIC)                       # partition -> high watermark
         committed = committed_offsets(GROUP_ID, TOPIC)   # partition -> committed offset, or -1
         slot_lag_bytes = fetch_slot_lag_bytes()
      2. snapshot_id = next_snapshot_id(conn)
      3. For each partition (iterate over high's keys, sorted for
         determinism):
           committed_offset = committed.get(partition, -1)
           consumer_lag = high[partition] if committed_offset < 0 else high[partition] - committed_offset
           consumer_lag = max(consumer_lag, 0)
           alert = (consumer_lag > ALERT_CONSUMER_LAG_THRESHOLD) or (
               slot_lag_bytes is not None and slot_lag_bytes > ALERT_SLOT_LAG_BYTES_THRESHOLD
           )
         Insert one row per partition into ops.cap_lag_snapshots with
         (snapshot_id, TOPIC, GROUP_ID, partition, high[partition],
         committed_offset, consumer_lag, slot_lag_bytes, alert).
      4. conn.commit() once, after all the inserts for this snapshot -- so
         a snapshot is either fully written or not written at all.
      5. Return snapshot_id.
    """
    raise NotImplementedError


def main() -> None:
    conn = mart_connect()
    ensure_ops_table(conn)
    record_snapshot(conn)
    conn.close()


if __name__ == "__main__":
    main()
