"""Validator for 08-cdc-debezium task 02 -- change-event-anatomy.

Registers a throwaway Debezium connector (s08-t02), lets its snapshot phase
land, applies a deterministic insert/update/delete burst directly against
the source, runs the learner's src/anatomy.py against the resulting topic,
then checks that (1) every op was tallied exactly and (2) every updated
offer's price was decoded byte-for-byte correctly out of the Kafka Connect
Decimal encoding.

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
    debezium_pg_connector_config,
    delete_connector,
    drop_publication,
    drop_slot,
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

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

CONNECTOR_NAME = "s08-t02"
SLOT_NAME = "s08_t02_slot"
PUB_NAME = "s08_t02_pub"
TOPIC_PREFIX = "s08.t02"

ANATOMY_SCRIPT = TASK_ROOT / "src" / "anatomy.py"

WORKLOAD_SEED = 2
N_INSERT = 200
N_UPDATE = 300
N_DELETE = 100

CONNECTOR_WAIT_TIMEOUT = 60
SLOT_INACTIVE_TIMEOUT = 15
STREAM_SETTLE_SECONDS = 5
ANATOMY_TIMEOUT = 180
RESEED_TIMEOUT = 120


def _tail(result, n=1500):
    return (result.stdout or "")[-n:] + (result.stderr or "")[-n:]


def _wait_slot_inactive(conn, slot_name, timeout=SLOT_INACTIVE_TIMEOUT):
    """A just-deleted connector's replication slot briefly reports
    active=true (its DB connection hasn't closed yet) -- dropping it in
    that window raises ObjectInUse. Poll until inactive or a fixed
    connection closes it out anyway."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        slots = {s["slot_name"]: s for s in replication_slots(conn)}
        slot = slots.get(slot_name)
        if slot is None or not slot["active"]:
            return
        time.sleep(1)


def _drop_ops_tables(conn):
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute("DROP TABLE IF EXISTS ops.t02_change_summary")
    cur.execute("DROP TABLE IF EXISTS ops.t02_decoded_prices")
    conn.commit()


def _offers_count():
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM shop.offers")
        return cur.fetchone()[0]
    finally:
        conn.close()


def _apply_workload_and_capture_prices(ops):
    """Applies ops to shop.offers, then reads back the CURRENT price for
    every updated offer_id (the exact value the learner's decoded output
    must match)."""
    conn = source_connect()
    try:
        cur = conn.cursor()
        for op in ops:
            if op["op"] == "update":
                cur.execute(
                    "UPDATE shop.offers SET price = %s, in_stock = %s, updated_at = now() "
                    "WHERE offer_id = %s",
                    (op["price"], op["in_stock"], op["offer_id"]),
                )
            elif op["op"] == "delete":
                cur.execute("DELETE FROM shop.offers WHERE offer_id = %s", (op["offer_id"],))
            elif op["op"] == "insert":
                cur.execute(
                    "INSERT INTO shop.offers "
                    "(offer_id, product_id, seller, price, currency, in_stock) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        op["offer_id"], op["product_id"], op["seller"],
                        op["price"], op["currency"], op["in_stock"],
                    ),
                )
        conn.commit()

        updated_ids = [op["offer_id"] for op in ops if op["op"] == "update"]
        cur.execute("SELECT offer_id, price FROM shop.offers WHERE offer_id = ANY(%s)", (updated_ids,))
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _run_anatomy(timeout):
    try:
        return subprocess.run(
            ["uv", "run", "python", str(ANATOMY_SCRIPT)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def _read_change_summary():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT op, n FROM ops.t02_change_summary")
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _read_decoded_prices():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT offer_id, price FROM ops.t02_decoded_prices")
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _teardown_connector_and_topics():
    delete_connector(CONNECTOR_NAME)
    conn = source_connect()
    try:
        _wait_slot_inactive(conn, SLOT_NAME)
        drop_slot(conn, SLOT_NAME)
        drop_publication(conn, PUB_NAME)
    finally:
        conn.close()
    reset_topics(TOPIC_PREFIX + ".")


def _final_cleanup():
    """Runs no matter how main() exits (pass, NOT PASSED, or crash) so a
    failed run never leaves an orphaned connector/slot pinning WAL on the
    source, or a mutated source left behind for the next task."""
    try:
        _teardown_connector_and_topics()
    except Exception as e:
        print(f"WARNING: connector/topic cleanup failed: {e}", file=sys.stderr)

    try:
        conn = mart_connect()
        try:
            _drop_ops_tables(conn)
        finally:
            conn.close()
    except Exception as e:
        print(f"WARNING: ops table cleanup failed: {e}", file=sys.stderr)

    try:
        reseed = subprocess.run(
            ["uv", "run", "python", "generate.py"],
            cwd=str(MODULE_ROOT), capture_output=True, text=True, timeout=RESEED_TIMEOUT,
        )
        if reseed.returncode != 0:
            print(f"WARNING: source reseed failed during cleanup: {_tail(reseed)}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: source reseed failed during cleanup: {e}", file=sys.stderr)


@guarded
def main():
    if not ANATOMY_SCRIPT.exists():
        not_passed(f"src/anatomy.py not found at {ANATOMY_SCRIPT}")

    gt = load_ground_truth()
    expected_offers = gt["row_counts"]["offers"]

    try:
        # 1. Clean slate for t02.
        _teardown_connector_and_topics()
        conn = mart_connect()
        try:
            _drop_ops_tables(conn)
        finally:
            conn.close()

        # 2. Ensure source is seeded to the documented ground truth.
        if _offers_count() != expected_offers:
            reseed = subprocess.run(
                ["uv", "run", "python", "generate.py"],
                cwd=str(MODULE_ROOT), capture_output=True, text=True, timeout=RESEED_TIMEOUT,
            )
            if reseed.returncode != 0:
                not_passed(f"source reseed failed: {_tail(reseed)}")
            if _offers_count() != expected_offers:
                not_passed(
                    f"shop.offers has {_offers_count()} rows, expected {expected_offers} "
                    "(ground truth) even after reseeding"
                )

        # 3. Register the connector, wait for snapshot + streaming to be RUNNING.
        connector_def = debezium_pg_connector_config(
            CONNECTOR_NAME, TOPIC_PREFIX, SLOT_NAME, PUB_NAME, "shop.offers",
        )
        register_connector(connector_def)
        wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECTOR_WAIT_TIMEOUT)

        # 4. Deterministic insert/update/delete burst against the source.
        ops = build_workload(WORKLOAD_SEED, n_insert=N_INSERT, n_update=N_UPDATE, n_delete=N_DELETE)
        expected_prices = _apply_workload_and_capture_prices(ops)
        time.sleep(STREAM_SETTLE_SECONDS)  # let the connector pick up the burst

        # 5. Run the learner's consumer.
        result = _run_anatomy(ANATOMY_TIMEOUT)
        if result is None:
            not_passed(f"src/anatomy.py did not exit within {ANATOMY_TIMEOUT}s")
        if result.returncode != 0:
            not_passed(f"src/anatomy.py exited {result.returncode}: {_tail(result)}")

        # 6. Op tally must be exact.
        counts = _read_change_summary()
        expected_counts = {"r": expected_offers, "c": N_INSERT, "u": N_UPDATE, "d": N_DELETE}
        for op, expected in expected_counts.items():
            actual = counts.get(op, 0)
            if actual != expected:
                not_passed(
                    f"ops.t02_change_summary: op={op!r} counted {actual}, expected {expected} "
                    f"(full summary: {counts})"
                )

        # 7. Decoded prices must match the source EXACTLY.
        decoded = _read_decoded_prices()
        missing = [oid for oid in expected_prices if oid not in decoded]
        if missing:
            not_passed(
                f"ops.t02_decoded_prices is missing {len(missing)} updated offer_ids, "
                f"e.g. {missing[:5]}"
            )
        mismatched = [
            (oid, decoded[oid], exp) for oid, exp in expected_prices.items() if decoded[oid] != exp
        ]
        if mismatched:
            oid, got, exp = mismatched[0]
            not_passed(
                f"ops.t02_decoded_prices offer_id={oid} decoded price {got}, expected {exp} "
                f"exactly ({len(mismatched)} of {len(expected_prices)} mismatched) -- "
                "the Decimal decode is wrong"
            )

        passed(
            f"tally exact (r={expected_offers} c={N_INSERT} u={N_UPDATE} d={N_DELETE}) and all "
            f"{len(expected_prices)} updated prices decoded exactly"
        )
    finally:
        _final_cleanup()


if __name__ == "__main__":
    main()
