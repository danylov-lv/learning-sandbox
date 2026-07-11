"""Validator for 08-cdc-debezium task 01 -- connector-setup-snapshot-vs-streaming.

Registers the learner's connector (via their src/register.py), then proves
both connector phases happened by counting op codes on the resulting Kafka
topics: an exact op="r" count per table for the snapshot phase, and
op in {"c","u","d"} showing up after a scripted insert/update/delete for
the streaming phase. Cleans up its own connector/slot/publication/topics
both before and after, and restores the source to its stock seed.

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
    decode_value,
    delete_connector,
    drain,
    drop_publication,
    drop_slot,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    replication_slots,
    reset_topics,
    source_connect,
    wait_for_connector_running,
)

CONNECTOR_NAME = "s08-t01"
SLOT_NAME = "s08_t01_slot"
PUB_NAME = "s08_t01_pub"
TOPIC_PREFIX = "s08.t01"
OFFERS_TOPIC = "s08.t01.shop.offers"
PRODUCTS_TOPIC = "s08.t01.shop.products"

REGISTER_SCRIPT = TASK_ROOT / "src" / "register.py"
REGISTER_TIMEOUT = 90
CONNECTOR_RUNNING_TIMEOUT = 60
SNAPSHOT_DRAIN_TIMEOUT = 60.0
STREAM_DRAIN_TIMEOUT = 60.0

INSERT_OFFER_ID = 9_000_001
INSERT_PRODUCT_ID = 1
UPDATE_OFFER_ID = 5
DELETE_OFFER_ID = 6
UPDATE_PRICE = 199.99


def _drop_slot_when_inactive(conn, name, attempts=8, interval=2.0):
    """The connector's replication connection can take a few seconds to
    close after delete_connector() returns -- an orphaned-but-still-active
    slot makes drop_slot() raise ObjectInUse. Poll active=false first, then
    fall back to a couple of blind retries (see .authoring/notes-infra.md
    for the gotcha this works around)."""
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


def _run_register():
    if not REGISTER_SCRIPT.exists():
        not_passed(f"src/register.py not found at {REGISTER_SCRIPT}")
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(REGISTER_SCRIPT)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=REGISTER_TIMEOUT,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"src/register.py did not exit within {REGISTER_TIMEOUT}s")
    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        not_passed(f"src/register.py exited {result.returncode} -- output tail:\n{tail}")


def _op_counts(topic, timeout):
    events = drain(topic, from_beginning=True, timeout=timeout)
    counts = {}
    for _key, raw in events:
        payload = decode_value(raw)
        op, _before, _after = change_op(payload)
        counts[op] = counts.get(op, 0) + 1
    return counts


def _apply_streaming_ops():
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO shop.offers (offer_id, product_id, seller, price, currency, in_stock) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (INSERT_OFFER_ID, INSERT_PRODUCT_ID, "ValidatorSeller", 42.42, "USD", True),
        )
        cur.execute(
            "UPDATE shop.offers SET price = %s WHERE offer_id = %s",
            (UPDATE_PRICE, UPDATE_OFFER_ID),
        )
        cur.execute("DELETE FROM shop.offers WHERE offer_id = %s", (DELETE_OFFER_ID,))
        conn.commit()
    finally:
        conn.close()


@guarded
def main():
    gt = load_ground_truth()

    _clean_slate()
    _check_source_seeded(gt)

    _run_register()
    wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECTOR_RUNNING_TIMEOUT)

    try:
        # --- snapshot phase ---
        offers_counts = _op_counts(OFFERS_TOPIC, SNAPSHOT_DRAIN_TIMEOUT)
        expected_offers = gt["row_counts"]["offers"]
        if offers_counts.get("r", 0) != expected_offers:
            not_passed(
                f"{OFFERS_TOPIC} has {offers_counts.get('r', 0)} op=r events, expected exactly "
                f"{expected_offers} (one per source row) -- op counts seen: {offers_counts}"
            )

        products_counts = _op_counts(PRODUCTS_TOPIC, SNAPSHOT_DRAIN_TIMEOUT)
        expected_products = gt["row_counts"]["products"]
        if products_counts.get("r", 0) != expected_products:
            not_passed(
                f"{PRODUCTS_TOPIC} has {products_counts.get('r', 0)} op=r events, expected exactly "
                f"{expected_products} -- op counts seen: {products_counts}"
            )

        # --- streaming phase ---
        _apply_streaming_ops()

        events = drain(OFFERS_TOPIC, from_beginning=True, timeout=STREAM_DRAIN_TIMEOUT)
        ops_seen = set()
        update_before = "unset"
        for _key, raw in events:
            payload = decode_value(raw)
            op, before, _after = change_op(payload)
            ops_seen.add(op)
            if op == "u":
                update_before = before

        missing = {"c", "u", "d"} - ops_seen
        if missing:
            not_passed(
                f"{OFFERS_TOPIC} never showed op(s) {sorted(missing)} after insert/update/delete "
                f"-- ops seen: {sorted(o for o in ops_seen if o is not None)}"
            )
        if update_before is None:
            not_passed(
                "the op=u event's `before` was null -- expected the full pre-image "
                "(REPLICA IDENTITY FULL is set on shop.offers, so before should be populated)"
            )

        passed(
            f"snapshot: {expected_offers} offers + {expected_products} products op=r events; "
            f"streaming: ops {sorted(o for o in ops_seen if o is not None)} observed with a "
            "populated before-image on the update"
        )
    finally:
        _clean_slate()
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


if __name__ == "__main__":
    main()
