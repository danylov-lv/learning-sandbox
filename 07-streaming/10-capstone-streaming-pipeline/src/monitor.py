"""s07.t10 lag monitor -- one lag snapshot for the capstone pipeline's
consumer group, per invocation. A lighter version of task 06's monitor: no
alerting, just a snapshot, because the capstone's grading is about the
aggregate tables staying correct across crashes/rebalances -- lag is here
to prove you can still SEE what the pipeline is doing while that happens.

CLI contract (what the validators rely on):

    uv run python src/monitor.py

Behavior contract:
- Takes exactly ONE snapshot of consumer-group lag for GROUP_ID
  ("t10-pipeline") against TOPIC ("s07.t10.price-updates"), then exits 0.
  It does not consume any messages from TOPIC -- only broker metadata
  (watermarks, committed offsets) for that group/topic pair.
- Writes one row PER PARTITION into ops.t10_lag_snapshots for this
  snapshot.
- Safe to run repeatedly: each run appends a new snapshot_id, it never
  overwrites or deletes a prior snapshot.

The one thing to implement: for each partition of TOPIC, compute
    lag = high_watermark - committed_offset
(an uncommitted partition has committed_offset == -1, which counts as full
backlog -- lag = high_watermark; floor at 0). Persist the per-partition
breakdown.

Reuse the primitives from harness.common, same as task 06:
harness.common.end_offsets(topic) and
harness.common.committed_offsets(group, topic). Do not reach for
harness.common.consumer_lag() as your answer -- it returns a single total
integer; this task is graded on the per-partition breakdown persisted to
Postgres.

psycopg gotcha on this build (3.x): do not use `with conn:` as a
transaction context manager -- it can close the connection on __exit__,
not just end the transaction. Use an explicit cursor + conn.commit(),
same pattern as ensure_ops_table below.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import committed_offsets, end_offsets, pg_connect  # noqa: E402

TOPIC = "s07.t10.price-updates"
GROUP_ID = "t10-pipeline"

OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops.t10_lag_snapshots (
    snapshot_id      BIGINT NOT NULL,
    topic            TEXT   NOT NULL,
    group_id         TEXT   NOT NULL,
    partition        INT    NOT NULL,
    high_watermark   BIGINT NOT NULL,
    committed_offset BIGINT NOT NULL,
    lag              BIGINT NOT NULL,
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
    cur.execute("SELECT COALESCE(MAX(snapshot_id), 0) + 1 FROM ops.t10_lag_snapshots")
    return cur.fetchone()[0]


def main() -> None:
    conn = pg_connect()
    ensure_ops_table(conn)

    # TODO: implement the one snapshot this task is graded on.
    #
    #   1. high = end_offsets(TOPIC)                    # partition -> high watermark
    #      committed = committed_offsets(GROUP_ID, TOPIC)  # partition -> committed offset, or -1
    #   2. snapshot_id = next_snapshot_id(conn)
    #   3. For each partition (iterate over high's keys, sorted for determinism):
    #        committed_offset = committed.get(partition, -1)
    #        lag = high[partition] if committed_offset < 0 else high[partition] - committed_offset
    #        lag = max(lag, 0)
    #      Insert one row per partition into ops.t10_lag_snapshots with
    #      (snapshot_id, TOPIC, GROUP_ID, partition, high[partition],
    #      committed_offset, lag).
    #   4. conn.commit() once, after all the inserts for this snapshot -- so
    #      a snapshot is either fully written or not written at all.
    raise NotImplementedError

    conn.close()


if __name__ == "__main__":
    main()
