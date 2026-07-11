"""Validator for 08-cdc-debezium task 05 -- replica-lag-and-alerting.

Two deterministic phases against a fresh connector s08-t05:

  Phase 1 (caught up): after the connector's snapshot phase lands on
  s08.t05.shop.offers, the materializer group's committed offsets are set
  (without consuming a single message -- a manual offset commit, same
  trick module 07's lag-monitoring validator uses) to exactly the current
  high watermark, so consumer lag is provably zero. The learner's monitor
  must record consumer_lag=0, alert=FALSE.

  Phase 2 (fallen behind): a deterministic insert/update/delete burst is
  applied to the source and allowed to stream onto the topic, but the
  materializer group's committed offsets are never advanced -- consumer
  lag becomes the size of the burst, comfortably over threshold. The
  learner's monitor must record consumer_lag over threshold, alert=TRUE,
  and a positive slot_lag_bytes (the source hasn't flushed the burst's WAL
  off the slot yet).

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    consumer_lag,
    debezium_pg_connector_config,
    delete_connector,
    drop_publication,
    drop_slot,
    end_offsets,
    guarded,
    kafka_bootstrap,
    load_ground_truth,
    mart_connect,
    not_passed,
    passed,
    register_connector,
    reset_topics,
    source_connect,
    wait_for_connector_running,
)
from generate import build_workload  # noqa: E402

os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

CONNECTOR_NAME = "s08-t05"
SLOT_NAME = "s08_t05_slot"
PUB_NAME = "s08_t05_pub"
TOPIC_PREFIX = "s08.t05"
TOPIC = "s08.t05.shop.offers"
GROUP_ID = "t05-materializer"
MONITOR_SCRIPT = TASK_ROOT / "src" / "monitor.py"

LAG_THRESHOLD = 1000
CONNECT_RUN_TIMEOUT = 60
SNAPSHOT_WAIT_TIMEOUT = 120
BURST_WAIT_TIMEOUT = 180
MONITOR_RUN_TIMEOUT = 60

WORKLOAD_SEED = 5
N_INSERT = 1200
N_UPDATE = 1500
N_DELETE = 300
# tombstones.on.delete=true (the connector default) publishes a tombstone
# record right after every delete's own op=d event -- two Kafka messages
# per deleted row, one Kafka message per insert/update.
EXPECTED_BURST_MESSAGES = N_INSERT + N_UPDATE + 2 * N_DELETE


def _last_line(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _drop_slot_safe(conn, name, attempts=8, delay=2.0):
    """drop_slot() can raise ObjectInUse for a few seconds right after a
    connector is deleted (its replication connection hasn't closed yet --
    see .authoring/design.md). Retry instead of failing the whole run."""
    import psycopg

    for i in range(attempts):
        try:
            return drop_slot(conn, name)
        except psycopg.errors.ObjectInUse:
            conn.rollback()
            if i == attempts - 1:
                not_passed(f"replication slot {name} still active after {attempts} attempts to drop it")
            time.sleep(delay)


def _full_teardown():
    delete_connector(CONNECTOR_NAME)
    source = source_connect()
    try:
        _drop_slot_safe(source, SLOT_NAME)
        drop_publication(source, PUB_NAME)
    finally:
        source.close()
    reset_topics(f"{TOPIC_PREFIX}.")


def _drop_snapshot_table():
    mart = mart_connect()
    try:
        cur = mart.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
        cur.execute("DROP TABLE IF EXISTS ops.t05_lag_snapshots")
        mart.commit()
    finally:
        mart.close()


def _sum_offsets(offsets):
    return sum(offsets.values())


def _wait_for_topic_total(topic, target, timeout, poll=2.0):
    deadline = time.time() + timeout
    last = 0
    while time.time() < deadline:
        offs = end_offsets(topic)
        last = _sum_offsets(offs)
        if last >= target:
            return offs
        time.sleep(poll)
    not_passed(
        f"topic {topic} only reached {last} messages within {timeout}s, expected at least {target}"
    )


def _commit_exact_offsets(topic, group, offsets):
    """Commit the group's offsets to exactly `offsets` (partition -> offset)
    without consuming any messages -- puts the group at zero lag as a known
    starting point, deterministically."""
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": group,
        "enable.auto.commit": False,
    })
    try:
        tps = [TopicPartition(topic, p, offsets[p]) for p in offsets]
        consumer.commit(offsets=tps, asynchronous=False)
    finally:
        consumer.close()


def _apply_workload(conn, ops):
    cur = conn.cursor()
    for op in ops:
        kind = op["op"]
        if kind == "update":
            cur.execute(
                "UPDATE shop.offers SET price=%s, in_stock=%s, updated_at=now() WHERE offer_id=%s",
                (op["price"], op["in_stock"], op["offer_id"]),
            )
        elif kind == "delete":
            cur.execute("DELETE FROM shop.offers WHERE offer_id=%s", (op["offer_id"],))
        elif kind == "insert":
            cur.execute(
                "INSERT INTO shop.offers (offer_id, product_id, seller, price, currency, in_stock) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (op["offer_id"], op["product_id"], op["seller"], op["price"], op["currency"], op["in_stock"]),
            )
        else:
            not_passed(f"unknown workload op {kind!r} from build_workload")
    conn.commit()


def _run_monitor(timeout):
    env = os.environ.copy()
    env["S08_LAG_THRESHOLD"] = str(LAG_THRESHOLD)
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


def _read_latest_snapshot(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT snapshot_id, consumer_lag, slot_lag_bytes, alert "
        "FROM ops.t05_lag_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        not_passed("ops.t05_lag_snapshots has no rows after running the monitor")
    return {"snapshot_id": row[0], "consumer_lag": row[1], "slot_lag_bytes": row[2], "alert": row[3]}


def _count_snapshots(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM ops.t05_lag_snapshots")
    return cur.fetchone()[0]


def _reseed_source():
    result = subprocess.run(
        ["uv", "run", "python", "generate.py"],
        cwd=str(MODULE_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        not_passed(f"reseeding via generate.py failed: {_last_line(result.stderr or result.stdout)}")


def _final_cleanup():
    """Runs no matter how main() exits (pass, NOT PASSED, or crash) so a
    failed run never leaves an orphaned connector/slot pinning WAL on the
    source, or a mutated source left behind for the next task."""
    try:
        _full_teardown()
    except Exception as e:
        print(f"WARNING: connector/topic cleanup failed: {e}", file=sys.stderr)

    try:
        _drop_snapshot_table()
    except Exception as e:
        print(f"WARNING: ops table cleanup failed: {e}", file=sys.stderr)

    try:
        _reseed_source()
    except SystemExit:
        raise
    except Exception as e:
        print(f"WARNING: source reseed failed during cleanup: {e}", file=sys.stderr)


@guarded
def main():
    if not MONITOR_SCRIPT.exists():
        not_passed(f"src/monitor.py not found at {MONITOR_SCRIPT}")

    # --- 1. clean slate.
    _full_teardown()
    _drop_snapshot_table()

    try:
        # --- 2. source must already be seeded.
        gt = load_ground_truth()
        source = source_connect()
        try:
            cur = source.cursor()
            cur.execute("SELECT count(*) FROM shop.offers")
            n_offers = cur.fetchone()[0]
        finally:
            source.close()
        expected_offers = gt["row_counts"]["offers"]
        if n_offers != expected_offers:
            not_passed(
                f"source not seeded: shop.offers has {n_offers} rows, expected {expected_offers} "
                "-- run `uv run python generate.py` first"
            )

        # --- 3. register connector t05 (twice, proving idempotent re-registration).
        config = debezium_pg_connector_config(
            CONNECTOR_NAME, TOPIC_PREFIX, SLOT_NAME, PUB_NAME, "shop.offers,shop.products",
        )
        register_connector(config)
        register_connector(config)
        wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECT_RUN_TIMEOUT)

        # --- 4. PHASE 1: wait for the snapshot to fully land, then put the
        # materializer group at exactly zero lag without consuming anything.
        baseline_offsets = _wait_for_topic_total(TOPIC, expected_offers, SNAPSHOT_WAIT_TIMEOUT)
        baseline_total = _sum_offsets(baseline_offsets)
        if baseline_total != expected_offers:
            not_passed(
                f"topic {TOPIC} has {baseline_total} messages after the snapshot, expected exactly {expected_offers}"
            )
        _commit_exact_offsets(TOPIC, GROUP_ID, baseline_offsets)

        caught_up_lag = consumer_lag(GROUP_ID, TOPIC)
        if caught_up_lag != 0:
            not_passed(f"consumer_lag({GROUP_ID!r}, {TOPIC!r}) is {caught_up_lag} right after committing to the high watermark, expected 0")

        r1 = _run_monitor(MONITOR_RUN_TIMEOUT)
        if r1 is None:
            not_passed(f"first monitor run did not exit within {MONITOR_RUN_TIMEOUT}s")
        if r1.returncode != 0:
            not_passed(f"first monitor run exited {r1.returncode} -- {_last_line(r1.stderr or r1.stdout)}")

        mart = mart_connect()
        try:
            if _count_snapshots(mart) != 1:
                not_passed(f"expected exactly 1 row in ops.t05_lag_snapshots after the first run, found {_count_snapshots(mart)}")
            snap1 = _read_latest_snapshot(mart)
        finally:
            mart.close()

        if snap1["consumer_lag"] != 0:
            not_passed(f"snapshot {snap1['snapshot_id']}: consumer_lag={snap1['consumer_lag']}, expected 0 (caught up)")
        if snap1["alert"] is not False:
            not_passed(f"snapshot {snap1['snapshot_id']}: alert={snap1['alert']}, expected FALSE (caught up)")

        # --- 5. PHASE 2: apply a burst, let it stream, but never advance the
        # materializer group's committed offsets.
        ops = build_workload(seed=WORKLOAD_SEED, n_insert=N_INSERT, n_update=N_UPDATE, n_delete=N_DELETE)
        source = source_connect()
        try:
            _apply_workload(source, ops)
        finally:
            source.close()

        target_total = baseline_total + EXPECTED_BURST_MESSAGES
        burst_offsets = _wait_for_topic_total(TOPIC, target_total, BURST_WAIT_TIMEOUT)
        burst_total = _sum_offsets(burst_offsets)

        behind_lag = consumer_lag(GROUP_ID, TOPIC)
        if behind_lag <= LAG_THRESHOLD:
            not_passed(
                f"consumer_lag({GROUP_ID!r}, {TOPIC!r})={behind_lag} after the burst, expected > {LAG_THRESHOLD} "
                f"(committed offsets should not have moved; topic grew from {baseline_total} to {burst_total})"
            )

        r2 = _run_monitor(MONITOR_RUN_TIMEOUT)
        if r2 is None:
            not_passed(f"second monitor run did not exit within {MONITOR_RUN_TIMEOUT}s")
        if r2.returncode != 0:
            not_passed(f"second monitor run exited {r2.returncode} -- {_last_line(r2.stderr or r2.stdout)}")

        mart = mart_connect()
        try:
            snap_count = _count_snapshots(mart)
            if snap_count != 2:
                not_passed(f"expected exactly 2 rows in ops.t05_lag_snapshots after the second run, found {snap_count}")
            snap2 = _read_latest_snapshot(mart)
        finally:
            mart.close()

        if snap2["snapshot_id"] == snap1["snapshot_id"]:
            not_passed("second monitor run did not add a new snapshot row (same snapshot_id as the first)")
        if snap2["consumer_lag"] < LAG_THRESHOLD:
            not_passed(f"snapshot {snap2['snapshot_id']}: consumer_lag={snap2['consumer_lag']}, expected >= {LAG_THRESHOLD}")
        if snap2["alert"] is not True:
            not_passed(f"snapshot {snap2['snapshot_id']}: alert={snap2['alert']}, expected TRUE (consumer_lag={snap2['consumer_lag']} > threshold={LAG_THRESHOLD})")
        if snap2["slot_lag_bytes"] <= 0:
            not_passed(
                f"snapshot {snap2['snapshot_id']}: slot_lag_bytes={snap2['slot_lag_bytes']}, expected > 0 "
                "(the burst's WAL should not be fully flushed off the slot yet)"
            )

        passed(
            f"phase 1 snapshot {snap1['snapshot_id']}: consumer_lag=0, alert=FALSE; "
            f"phase 2 snapshot {snap2['snapshot_id']}: consumer_lag={snap2['consumer_lag']}, "
            f"alert=TRUE, slot_lag_bytes={snap2['slot_lag_bytes']}"
        )
    finally:
        _final_cleanup()


if __name__ == "__main__":
    main()
