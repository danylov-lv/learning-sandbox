"""s07.t06 lag monitor -- one snapshot of consumer-group lag per invocation.

CLI contract (what the validator relies on):

    uv run python src/monitor.py

Behavior contract:
- Takes exactly ONE snapshot of consumer-group lag for GROUP_ID
  ("t06-consumer") against TOPIC ("s07.t06.price-updates"), then exits 0.
  It is NOT a long-running poll loop and it does not consume any messages
  from TOPIC -- it only reads broker metadata (watermarks, committed
  offsets) for that group/topic pair.
- Writes one row PER PARTITION into ops.t06_lag_snapshots for this
  snapshot, plus one row into ops.t06_alerts IFF this snapshot's total lag
  (summed across partitions) exceeds S07_LAG_THRESHOLD (env, default
  50000).
- Safe to run repeatedly: each run appends a new snapshot_id, it never
  overwrites or deletes a prior snapshot.

The one thing you must implement: for each partition of TOPIC, compute
    lag = high_watermark - committed_offset
(with an uncommitted partition, committed_offset == -1, counting as full
backlog -- treat that case as lag = high_watermark, i.e. floor at 0 same
as the low-watermark story elsewhere in this module; every topic here
starts at offset 0, so "high - low" and "high" coincide), persist the
per-partition breakdown, sum it, and raise an alert row when the sum
crosses the threshold.

IMPORTANT -- do NOT reach for harness.common.consumer_lag() as your answer.
It exists only as a reference oracle the validator uses to double-check
your work, and it returns a single total integer. This task grades a
PER-PARTITION breakdown persisted to Postgres -- a total alone can't give
you that. Build lag from the primitives instead:
harness.common.end_offsets(topic) and
harness.common.committed_offsets(group, topic).

psycopg gotcha on this build (3.x): do not use `with conn:` as a
transaction context manager -- it can close the connection on __exit__,
not just end the transaction. Use an explicit cursor + conn.commit(),
same pattern as ensure_ops_tables below.
"""

import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import committed_offsets, end_offsets, pg_connect  # noqa: E402

TOPIC = "s07.t06.price-updates"
GROUP_ID = "t06-consumer"
DEFAULT_LAG_THRESHOLD = 50000

OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops.t06_lag_snapshots (
    snapshot_id      BIGINT NOT NULL,
    topic            TEXT   NOT NULL,
    group_id         TEXT   NOT NULL,
    partition        INT    NOT NULL,
    high_watermark   BIGINT NOT NULL,
    committed_offset BIGINT NOT NULL,
    lag              BIGINT NOT NULL,
    captured_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.t06_alerts (
    snapshot_id BIGINT NOT NULL,
    total_lag   BIGINT NOT NULL,
    threshold   BIGINT NOT NULL,
    raised_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def ensure_ops_tables(conn) -> None:
    """Given plumbing. Creates the two tables this task is graded on, if
    they don't exist yet -- idempotent, safe to call on every run."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(OPS_DDL)
    conn.commit()


def lag_threshold() -> int:
    return int(os.environ.get("S07_LAG_THRESHOLD", str(DEFAULT_LAG_THRESHOLD)))


def next_snapshot_id(conn) -> int:
    """Given plumbing. Each run appends a new snapshot rather than
    overwriting a previous one."""
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(snapshot_id), 0) + 1 FROM ops.t06_lag_snapshots")
    return cur.fetchone()[0]


def main() -> None:
    conn = pg_connect()
    ensure_ops_tables(conn)

    # TODO: implement the one snapshot this task is graded on.
    #
    #   1. high = end_offsets(TOPIC)              # dict partition -> high watermark
    #      committed = committed_offsets(GROUP_ID, TOPIC)  # dict partition -> committed offset, or -1
    #   2. snapshot_id = next_snapshot_id(conn)
    #   3. For each partition (iterate over high's keys, sorted for determinism):
    #        committed_offset = committed.get(partition, -1)
    #        lag = high[partition] if committed_offset < 0 else high[partition] - committed_offset
    #        lag = max(lag, 0)
    #      Insert one row per partition into ops.t06_lag_snapshots with
    #      (snapshot_id, TOPIC, GROUP_ID, partition, high[partition],
    #      committed_offset, lag).
    #   4. total_lag = sum of all per-partition lag values just computed.
    #      threshold = lag_threshold()
    #      If total_lag > threshold: insert one row into ops.t06_alerts
    #      with (snapshot_id, total_lag, threshold).
    #   5. conn.commit() once, after all the inserts for this snapshot.
    #
    # Do this all in one Postgres transaction (one cursor, one commit at the
    # end) so a snapshot is either fully written or not written at all.
    raise NotImplementedError

    conn.close()


if __name__ == "__main__":
    main()
