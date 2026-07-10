"""Validator for 07-streaming task 06 -- lag-monitoring.

Produces half the corpus onto s07.t06.price-updates, then commits the
group's offsets to exactly the current high watermark (WITHOUT actually
consuming anything, via a manual commit) so lag starts at zero. Runs the
learner's monitor once and checks it recorded a zero-lag snapshot with no
alert. Then produces the second half (lag jumps by ~100000 since the
group's committed offsets don't move), runs the monitor a second time, and
checks it recorded the new per-partition lag exactly AND raised exactly
one alert row for that snapshot.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    committed_offsets,
    create_topic,
    end_offsets,
    guarded,
    iter_events,
    kafka_bootstrap,
    not_passed,
    passed,
    pg_connect,
    produce_events,
    reset_topics,
)

os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

TOPIC = "s07.t06.price-updates"
GROUP_ID = "t06-consumer"
MONITOR_SCRIPT = TASK_ROOT / "src" / "monitor.py"
LAG_THRESHOLD = 50000
RUN_TIMEOUT = 120
BATCH1_SIZE = 100000


def _drop_result_state(conn):
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute("DROP TABLE IF EXISTS ops.t06_lag_snapshots, ops.t06_alerts CASCADE")
    conn.commit()


def _commit_exact_offsets(offsets):
    """Commit the group's offsets to exactly `offsets` (partition -> offset)
    without consuming any messages -- puts the group at zero lag as a known
    starting point, deterministically."""
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
    })
    try:
        tps = [TopicPartition(TOPIC, p, offsets[p]) for p in offsets]
        consumer.commit(offsets=tps, asynchronous=False)
    finally:
        consumer.close()


def _last_line(text):
    """Last non-empty line of a subprocess stream -- enough to say WHY a run
    failed (e.g. `NotImplementedError`) without leaking a full traceback
    into the validator's own NOT PASSED output."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _run_monitor(timeout):
    env = os.environ.copy()
    env["S07_LAG_THRESHOLD"] = str(LAG_THRESHOLD)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(MONITOR_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def _read_snapshots(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT snapshot_id, partition, high_watermark, committed_offset, lag "
        "FROM ops.t06_lag_snapshots ORDER BY snapshot_id, partition"
    )
    rows = cur.fetchall()
    out = {}
    for snapshot_id, partition, high, committed, lag in rows:
        out.setdefault(snapshot_id, {})[partition] = {
            "high": high, "committed": committed, "lag": lag,
        }
    return out


def _read_alerts(conn):
    cur = conn.cursor()
    cur.execute("SELECT snapshot_id, total_lag, threshold FROM ops.t06_alerts ORDER BY snapshot_id")
    return cur.fetchall()


def _expected_lag_map(topic, group):
    high = end_offsets(topic)
    committed = committed_offsets(group, topic)
    out = {}
    for p, h in high.items():
        c = committed.get(p, -1)
        lag = h if c < 0 else h - c
        out[p] = {"high": h, "committed": c, "lag": max(lag, 0)}
    return out


@guarded
def main():
    if not MONITOR_SCRIPT.exists():
        not_passed(f"src/monitor.py not found at {MONITOR_SCRIPT}")

    corpus = list(iter_events())
    if len(corpus) < BATCH1_SIZE:
        not_passed(
            f"data/events.ndjson only has {len(corpus)} lines, need at least "
            f"{BATCH1_SIZE} -- regenerate the corpus first"
        )
    batch1 = corpus[:BATCH1_SIZE]
    batch2 = corpus[BATCH1_SIZE:]

    reset_topics("s07.t06.")
    create_topic(TOPIC, partitions=6)

    conn = pg_connect()
    try:
        _drop_result_state(conn)
    finally:
        conn.close()

    produced1 = produce_events(TOPIC, batch1, key_field="product_id")
    if produced1 != len(batch1):
        not_passed(f"produced {produced1} events for batch 1, expected {len(batch1)}")

    ends1 = end_offsets(TOPIC)
    if not ends1:
        not_passed(f"end_offsets({TOPIC!r}) returned nothing -- topic has no partitions?")
    _commit_exact_offsets(ends1)

    # --- monitor run 1: lag should be exactly zero, no alert.
    r1 = _run_monitor(RUN_TIMEOUT)
    if r1 is None:
        not_passed(f"first monitor run did not exit within {RUN_TIMEOUT}s")
    if r1.returncode != 0:
        not_passed(
            f"first monitor run exited {r1.returncode} -- {_last_line(r1.stderr or r1.stdout)}"
        )

    expected1 = _expected_lag_map(TOPIC, GROUP_ID)

    conn = pg_connect()
    try:
        snapshots = _read_snapshots(conn)
        alerts = _read_alerts(conn)
    finally:
        conn.close()

    if len(snapshots) != 1:
        not_passed(f"expected exactly 1 snapshot after the first run, found {len(snapshots)}")
    snap1_id = next(iter(snapshots))
    snap1 = snapshots[snap1_id]

    if set(snap1.keys()) != set(expected1.keys()):
        not_passed(
            f"snapshot {snap1_id} has partitions {sorted(snap1.keys())}, "
            f"expected {sorted(expected1.keys())}"
        )
    for p, exp in expected1.items():
        act = snap1[p]
        if act["high"] != exp["high"] or act["committed"] != exp["committed"] or act["lag"] != exp["lag"]:
            not_passed(
                f"snapshot {snap1_id} partition {p}: got high={act['high']} "
                f"committed={act['committed']} lag={act['lag']}, expected "
                f"high={exp['high']} committed={exp['committed']} lag={exp['lag']}"
            )
    total1 = sum(v["lag"] for v in snap1.values())
    if total1 != 0:
        not_passed(f"snapshot {snap1_id} total lag is {total1}, expected 0 (committed == high)")
    if alerts:
        not_passed(f"expected no alert rows after the zero-lag first run, found {len(alerts)}")

    # --- produce batch 2: high watermark rises, committed offsets unchanged.
    produced2 = produce_events(TOPIC, batch2, key_field="product_id")
    if produced2 != len(batch2):
        not_passed(f"produced {produced2} events for batch 2, expected {len(batch2)}")

    # --- monitor run 2: lag should equal len(batch2), one alert expected.
    r2 = _run_monitor(RUN_TIMEOUT)
    if r2 is None:
        not_passed(f"second monitor run did not exit within {RUN_TIMEOUT}s")
    if r2.returncode != 0:
        not_passed(
            f"second monitor run exited {r2.returncode} -- {_last_line(r2.stderr or r2.stdout)}"
        )

    expected2 = _expected_lag_map(TOPIC, GROUP_ID)

    conn = pg_connect()
    try:
        snapshots = _read_snapshots(conn)
        alerts = _read_alerts(conn)
    finally:
        conn.close()

    if len(snapshots) != 2:
        not_passed(f"expected exactly 2 snapshots after the second run, found {len(snapshots)}")
    snap_ids = sorted(snapshots.keys())
    if snap_ids[0] != snap1_id:
        not_passed(f"first snapshot id changed between runs: was {snap1_id}, now {snap_ids[0]}")
    snap2_id = snap_ids[1]
    snap2 = snapshots[snap2_id]

    if set(snap2.keys()) != set(expected2.keys()):
        not_passed(
            f"snapshot {snap2_id} has partitions {sorted(snap2.keys())}, "
            f"expected {sorted(expected2.keys())}"
        )
    for p, exp in expected2.items():
        act = snap2[p]
        if act["high"] != exp["high"] or act["committed"] != exp["committed"] or act["lag"] != exp["lag"]:
            not_passed(
                f"snapshot {snap2_id} partition {p}: got high={act['high']} "
                f"committed={act['committed']} lag={act['lag']}, expected "
                f"high={exp['high']} committed={exp['committed']} lag={exp['lag']}"
            )
    total2 = sum(v["lag"] for v in snap2.values())
    expected_total2 = len(batch2)
    if total2 != expected_total2:
        not_passed(
            f"snapshot {snap2_id} total lag is {total2}, expected {expected_total2} "
            "(size of the second produce batch, since committed offsets did not move)"
        )

    alerts_by_snapshot = {row[0]: row for row in alerts}
    if snap1_id in alerts_by_snapshot:
        not_passed(f"snapshot {snap1_id} (zero lag) unexpectedly has an alert row")
    if snap2_id not in alerts_by_snapshot:
        not_passed(
            f"snapshot {snap2_id} total_lag={total2} exceeds threshold={LAG_THRESHOLD} "
            "but no alert row was raised in ops.t06_alerts"
        )
    alert_count_for_snap2 = sum(1 for row in alerts if row[0] == snap2_id)
    if alert_count_for_snap2 != 1:
        not_passed(
            f"expected exactly 1 alert row for snapshot {snap2_id}, found {alert_count_for_snap2}"
        )
    _, alert_total_lag, alert_threshold = alerts_by_snapshot[snap2_id]
    if alert_total_lag != total2:
        not_passed(
            f"alert row for snapshot {snap2_id} has total_lag={alert_total_lag}, "
            f"expected {total2}"
        )
    if alert_threshold != LAG_THRESHOLD:
        not_passed(
            f"alert row for snapshot {snap2_id} has threshold={alert_threshold}, "
            f"expected {LAG_THRESHOLD}"
        )

    passed(
        f"snapshot {snap1_id} lag=0 (no alert); snapshot {snap2_id} lag={total2} "
        f"matches recomputed lag across {len(snap2)} partitions, alert raised with "
        f"total_lag={alert_total_lag} threshold={alert_threshold}"
    )


if __name__ == "__main__":
    main()
