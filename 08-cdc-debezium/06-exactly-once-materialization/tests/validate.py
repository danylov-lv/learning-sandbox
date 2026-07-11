"""Validator for 08-cdc-debezium task 06 -- exactly-once-materialization.

Registers connector s08-t06, drives the learner's src/materialize.py through
TWO injected mid-stream crashes and a final clean run, then checks TWO things
independently: replica.offers matches the live source shop.offers exactly,
and mart.t06_meta.applied_changes matches an INDEPENDENTLY drained count of
non-tombstone change events exactly -- proving the aggregate survived
redelivery without double-counting.

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

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

from harness.common import (  # noqa: E402
    change_op,
    debezium_pg_connector_config,
    decode_value,
    delete_connector,
    drain,
    drop_publication,
    drop_slot,
    end_offsets,
    guarded,
    load_ground_truth,
    mart_connect,
    not_passed,
    passed,
    register_connector,
    replication_slots,
    reset_topics,
    source_connect,
    wait_for_connector_running,
)
from generate import build_workload  # noqa: E402

CONNECTOR_NAME = "s08-t06"
SLOT_NAME = "s08_t06_slot"
PUB_NAME = "s08_t06_pub"
TOPIC_PREFIX = "s08.t06"
OFFERS_TOPIC = "s08.t06.shop.offers"

MATERIALIZE_SCRIPT = TASK_ROOT / "src" / "materialize.py"
CONNECTOR_RUNNING_TIMEOUT = 60
SNAPSHOT_DRAIN_TIMEOUT = 60.0
STREAM_CATCHUP_TIMEOUT = 120
CRASH_AFTER_1 = 8000
# _maybe_crash's `processed` counter resets to 0 at the start of every run
# (see src/materialize.py main()), so this is a PER-RUN threshold, not a
# cumulative stream position. With a 20000-row snapshot + 3100-message burst
# (23100 total) and crash run 1 consuming/committing ~8000 of them, only
# ~15100 messages remain for crash run 2 -- so its threshold must be well
# under that, not "18000" (which was never reachable in a single run and
# made the second crash a no-op). 10000 here lands the second crash at
# cumulative stream position ~18000 (8000 + 10000), matching the original
# "further into the stream" intent.
CRASH_AFTER_2 = 10000
CRASH_RUN_TIMEOUT = 300
FULL_RUN_TIMEOUT = 300
FINAL_DRAIN_TIMEOUT = 60.0
PRICE_TOLERANCE = 0.01

WORKLOAD_SEED = 6
N_INSERT = 800
N_UPDATE = 1500
N_DELETE = 400


def _drop_slot_when_inactive(conn, name, attempts=8, interval=2.0):
    import psycopg

    for _ in range(attempts):
        slots = replication_slots(conn)
        target = next((s for s in slots if s["slot_name"] == name), None)
        if target is None or not target["active"]:
            break
        time.sleep(interval)
    for attempt in range(3):
        try:
            return drop_slot(conn, name)
        except psycopg.errors.ObjectInUse:
            if attempt == 2:
                raise
            time.sleep(interval)


def _clean_slate():
    delete_connector(CONNECTOR_NAME)
    conn = source_connect()
    try:
        _drop_slot_when_inactive(conn, SLOT_NAME)
        drop_publication(conn, PUB_NAME)
    finally:
        conn.close()
    reset_topics(TOPIC_PREFIX)

    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS replica")
        cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
        cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
        cur.execute("DROP TABLE IF EXISTS replica.offers")
        cur.execute("DROP TABLE IF EXISTS mart.t06_meta")
        cur.execute("DROP TABLE IF EXISTS ops.t06_seen, ops.t06_offsets CASCADE")
        conn.commit()
    finally:
        conn.close()


def _check_source_seeded(gt):
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM shop.offers")
        offers_count = cur.fetchone()[0]
    finally:
        conn.close()
    expected = gt["row_counts"]["offers"]
    if offers_count != expected:
        not_passed(
            f"shop.offers has {offers_count} rows, expected {expected} -- "
            "run `uv run python generate.py` first"
        )


def _apply_burst(ops):
    conn = source_connect()
    try:
        cur = conn.cursor()
        for op in ops:
            if op["op"] == "update":
                cur.execute(
                    "UPDATE shop.offers SET price = %s, in_stock = %s WHERE offer_id = %s",
                    (op["price"], op["in_stock"], op["offer_id"]),
                )
            elif op["op"] == "delete":
                cur.execute("DELETE FROM shop.offers WHERE offer_id = %s", (op["offer_id"],))
            elif op["op"] == "insert":
                cur.execute(
                    "INSERT INTO shop.offers (offer_id, product_id, seller, price, currency, in_stock) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (op["offer_id"], op["product_id"], op["seller"], op["price"], op["currency"], op["in_stock"]),
                )
            else:
                not_passed(f"unknown op in build_workload output: {op['op']!r}")
        conn.commit()
    finally:
        conn.close()


def _wait_streaming_caught_up(topic, expected_total, timeout):
    """Poll the topic's high watermark until it reaches expected_total,
    proving Debezium has streamed every WAL record produced by the burst
    onto the topic before we start counting messages against a fixed corpus.

    NOTE: this used to poll replication_slots()'s lag_bytes (computed
    against restart_lsn) until it hit 0. That check is unreliable here:
    restart_lsn on a Postgres logical replication slot only advances on
    specific internal triggers (observed live: it can stay pinned well
    behind confirmed_flush_lsn indefinitely once the burst's writes stop,
    regardless of how long you wait or whether you generate more unrelated
    WAL activity afterward) -- it is not a synchronous function of "has
    Debezium drained the WAL it needs to." Task 05 deliberately measures
    lag via confirmed_flush_lsn instead of restart_lsn for exactly this
    reason (see its README/docstring). Waiting on the topic's own message
    count is a direct, reliable proxy for "the burst fully landed on Kafka"
    and matches what this function is actually trying to prove."""
    deadline = time.time() + timeout
    last_total = None
    while time.time() < deadline:
        last_total = sum(end_offsets(topic).values())
        if last_total >= expected_total:
            return
        time.sleep(2)
    not_passed(
        f"topic {topic} only reached {last_total} messages within {timeout}s, "
        f"expected at least {expected_total}"
    )


def _run_materialize(env_overrides, timeout):
    env = os.environ.copy()
    env.pop("S08_CRASH_AFTER", None)
    env.update(env_overrides)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(MATERIALIZE_SCRIPT)],
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


def _read_source_offers():
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT offer_id, product_id, seller, price, currency, in_stock FROM shop.offers")
        return {
            row[0]: {"product_id": row[1], "seller": row[2], "price": float(row[3]),
                      "currency": row[4], "in_stock": row[5]}
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def _read_replica_offers():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT offer_id, product_id, seller, price, currency, in_stock FROM replica.offers")
        return {
            row[0]: {"product_id": row[1], "seller": row[2], "price": float(row[3]),
                      "currency": row[4], "in_stock": row[5]}
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def _read_applied_changes():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT applied_changes FROM mart.t06_meta WHERE id = 1")
        except Exception as e:
            not_passed(f"could not read mart.t06_meta after the runs -- does it exist? {e}")
        row = cur.fetchone()
        if row is None:
            not_passed("mart.t06_meta has no row with id=1 -- expected a single seeded meta row")
        return row[0]
    finally:
        conn.close()


def _count_expected_non_tombstone_changes():
    events = drain(OFFERS_TOPIC, from_beginning=True, timeout=FINAL_DRAIN_TIMEOUT)
    expected = 0
    for _key, raw in events:
        payload = decode_value(raw)
        op, _before, _after = change_op(payload)
        if op is not None:
            expected += 1
    return expected


def _restore_source():
    try:
        subprocess.run(
            ["uv", "run", "python", "generate.py"],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:
        pass


@guarded
def main():
    if not MATERIALIZE_SCRIPT.exists():
        not_passed(f"src/materialize.py not found at {MATERIALIZE_SCRIPT}")

    gt = load_ground_truth()

    _clean_slate()
    _check_source_seeded(gt)

    connector_def = debezium_pg_connector_config(
        name=CONNECTOR_NAME,
        topic_prefix=TOPIC_PREFIX,
        slot_name=SLOT_NAME,
        publication_name=PUB_NAME,
        table_include_list="shop.offers",
        extra={"decimal.handling.mode": "double"},
    )

    try:
        register_connector(connector_def)
        wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECTOR_RUNNING_TIMEOUT)

        snapshot_events = drain(OFFERS_TOPIC, from_beginning=True, timeout=SNAPSHOT_DRAIN_TIMEOUT)
        snapshot_r = sum(
            1 for _key, raw in snapshot_events
            if change_op(decode_value(raw))[0] == "r"
        )
        expected_snapshot = gt["row_counts"]["offers"]
        if snapshot_r != expected_snapshot:
            not_passed(
                f"{OFFERS_TOPIC} snapshot has {snapshot_r} op=r events, expected exactly "
                f"{expected_snapshot} -- did the connector finish snapshotting?"
            )

        burst = build_workload(seed=WORKLOAD_SEED, n_insert=N_INSERT, n_update=N_UPDATE, n_delete=N_DELETE)
        _apply_burst(burst)
        # tombstones.on.delete=true publishes a tombstone right after every
        # delete's own op=d event -- two Kafka messages per deleted row.
        expected_after_burst = expected_snapshot + N_INSERT + N_UPDATE + 2 * N_DELETE
        _wait_streaming_caught_up(OFFERS_TOPIC, expected_after_burst, STREAM_CATCHUP_TIMEOUT)

        # --- crash run 1: kill mid-stream. Nonzero exit expected and tolerated.
        r1 = _run_materialize({"S08_CRASH_AFTER": str(CRASH_AFTER_1)}, CRASH_RUN_TIMEOUT)
        if r1 is None:
            not_passed(
                f"first crash run (S08_CRASH_AFTER={CRASH_AFTER_1}) did not exit within "
                f"{CRASH_RUN_TIMEOUT}s -- the crash hook should hard-exit almost immediately "
                "once it reaches the count"
            )
        if r1.returncode == 0:
            tail = (r1.stdout or "")[-1000:] + (r1.stderr or "")[-1000:]
            not_passed(
                f"first crash run (S08_CRASH_AFTER={CRASH_AFTER_1}) exited 0 -- expected a nonzero "
                f"exit from the injected os._exit(1) crash hook; is materialize.py calling "
                f"_maybe_crash? output tail:\n{tail}"
            )

        # --- crash run 2: kill mid-stream again, further in. Nonzero exit expected.
        r2 = _run_materialize({"S08_CRASH_AFTER": str(CRASH_AFTER_2)}, CRASH_RUN_TIMEOUT)
        if r2 is None:
            not_passed(
                f"second crash run (S08_CRASH_AFTER={CRASH_AFTER_2}) did not exit within "
                f"{CRASH_RUN_TIMEOUT}s"
            )
        if r2.returncode == 0:
            tail = (r2.stdout or "")[-1000:] + (r2.stderr or "")[-1000:]
            not_passed(
                f"second crash run (S08_CRASH_AFTER={CRASH_AFTER_2}) exited 0 -- expected a "
                f"nonzero exit from the injected crash hook; output tail:\n{tail}"
            )

        # --- clean run: no crash env, must catch up and exit 0.
        r3 = _run_materialize({}, FULL_RUN_TIMEOUT)
        if r3 is None:
            not_passed(
                f"final clean run did not exit within {FULL_RUN_TIMEOUT}s -- did it fail to "
                "reach idle-exit and catch up with the topic?"
            )
        if r3.returncode != 0:
            tail = (r3.stdout or "")[-1500:] + (r3.stderr or "")[-1500:]
            not_passed(f"final clean run exited {r3.returncode} -- output tail:\n{tail}")

        expected_changes = _count_expected_non_tombstone_changes()

        source_offers = _read_source_offers()
        replica_offers = _read_replica_offers()

        source_ids = set(source_offers.keys())
        replica_ids = set(replica_offers.keys())
        missing = source_ids - replica_ids
        extra = replica_ids - source_ids
        if missing:
            not_passed(f"replica.offers is missing {len(missing)} offer_id(s) present in shop.offers: {sorted(missing)[:10]}")
        if extra:
            not_passed(f"replica.offers has {len(extra)} extra offer_id(s) not in shop.offers: {sorted(extra)[:10]}")

        for offer_id, expected_row in source_offers.items():
            actual_row = replica_offers[offer_id]
            for field in ("product_id", "seller", "currency", "in_stock"):
                if actual_row[field] != expected_row[field]:
                    not_passed(
                        f"offer_id {offer_id}: replica.offers.{field}={actual_row[field]!r}, "
                        f"expected {expected_row[field]!r}"
                    )
            if abs(actual_row["price"] - expected_row["price"]) > PRICE_TOLERANCE:
                not_passed(
                    f"offer_id {offer_id}: replica.offers.price={actual_row['price']}, "
                    f"expected {expected_row['price']} (tolerance {PRICE_TOLERANCE})"
                )

        applied_changes = _read_applied_changes()
        if applied_changes != expected_changes:
            direction = "over" if applied_changes > expected_changes else "under"
            hint = (
                " -- this is double-counting from redelivery across a crash: the mart write "
                "and the applied_changes increment were not committed atomically with the "
                "dedup check"
                if direction == "over"
                else " -- an update was lost across a crash"
            )
            not_passed(
                f"mart.t06_meta.applied_changes = {applied_changes}, expected exactly "
                f"{expected_changes} (independently counted from the topic){hint}"
            )

        passed(
            f"replica.offers matches shop.offers exactly ({len(source_offers)} offers) after two "
            f"injected crashes (at {CRASH_AFTER_1} and {CRASH_AFTER_2} messages); "
            f"mart.t06_meta.applied_changes={applied_changes} matches the independently "
            f"drained non-tombstone event count exactly"
        )
    finally:
        _clean_slate()
        _restore_source()


if __name__ == "__main__":
    main()
