"""CP1 validator for 08-capstone-converge: steady pipeline, no injected
failures.

Clean-slates the s08.cap connector/slot/publication/topic and the mart
tables this pipeline maintains, ensures the source is seeded, registers the
connector (decimal.handling.mode=double), runs src/pipeline.py once against
the initial snapshot, applies a deterministic insert/update/delete burst
to the source, runs src/pipeline.py again (a resume), and asserts:

  1. replica.offers matches shop.offers exactly (check_converged, reused
     by CP2/CP3).
  2. mart.cap_meta.applied_changes equals an independently-drained count of
     non-tombstone events on the topic.

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    change_op,
    debezium_pg_connector_config,
    decode_value,
    delete_connector,
    drain,
    drop_publication,
    drop_slot,
    guarded,
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

CONNECTOR_NAME = "s08-cap"
SLOT_NAME = "s08_cap_slot"
PUBLICATION_NAME = "s08_cap_pub"
TOPIC_PREFIX = "s08.cap"
TOPIC = "s08.cap.shop.offers"

PIPELINE_SCRIPT = TASK_ROOT / "src" / "pipeline.py"
FIRST_RUN_TIMEOUT = 600
SECOND_RUN_TIMEOUT = 600
CONNECTOR_RUNNING_TIMEOUT = 60

PRICE_TOLERANCE = 0.01

WORKLOAD_SEED = 101
WORKLOAD_N_INSERT = 800
WORKLOAD_N_UPDATE = 1500
WORKLOAD_N_DELETE = 400


def _last_line(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def teardown_connector():
    delete_connector(CONNECTOR_NAME)
    conn = source_connect()
    try:
        try:
            drop_slot(conn, SLOT_NAME)
        except Exception:
            time.sleep(5)
            drop_slot(conn, SLOT_NAME)
        drop_publication(conn, PUBLICATION_NAME)
    finally:
        conn.close()
    reset_topics(TOPIC_PREFIX)


def drop_result_tables():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS replica")
        cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
        cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
        cur.execute(
            "DROP TABLE IF EXISTS replica.offers, mart.cap_meta, "
            "ops.cap_lag_snapshots, ops.cap_seen CASCADE"
        )
        conn.commit()
    finally:
        conn.close()


def restore_source_schema():
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE shop.offers DROP COLUMN IF EXISTS discount_pct")
        conn.commit()
    finally:
        conn.close()


def _row_counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM shop.products")
    n_products = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM shop.offers")
    n_offers = cur.fetchone()[0]
    return n_products, n_offers


def ensure_source_seeded():
    gt = load_ground_truth()
    expected_products = gt["row_counts"]["products"]
    expected_offers = gt["row_counts"]["offers"]

    conn = source_connect()
    try:
        n_products, n_offers = _row_counts(conn)
    finally:
        conn.close()

    if n_products == expected_products and n_offers == expected_offers:
        return

    try:
        subprocess.run(
            ["uv", "run", "python", "generate.py"],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        not_passed(f"source not seeded and could not run generate.py to reseed it: {e}")

    conn = source_connect()
    try:
        n_products, n_offers = _row_counts(conn)
    finally:
        conn.close()
    if n_products != expected_products or n_offers != expected_offers:
        not_passed(
            f"source still not seeded correctly after generate.py "
            f"(products={n_products}, offers={n_offers}, "
            f"expected products={expected_products}, offers={expected_offers})"
        )


def apply_workload(ops):
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
                    "(offer_id, product_id, seller, price, currency, in_stock, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, now())",
                    (
                        op["offer_id"], op["product_id"], op["seller"],
                        op["price"], op["currency"], op["in_stock"],
                    ),
                )
            else:
                not_passed(f"build_workload produced an unknown op: {op['op']!r}")
        conn.commit()
    finally:
        conn.close()


def register_cap_connector():
    connector_def = debezium_pg_connector_config(
        CONNECTOR_NAME, TOPIC_PREFIX, SLOT_NAME, PUBLICATION_NAME, "shop.offers",
        extra={"decimal.handling.mode": "double"},
    )
    register_connector(connector_def)
    wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECTOR_RUNNING_TIMEOUT)


def run_pipeline(env_overrides=None, timeout=FIRST_RUN_TIMEOUT):
    env = os.environ.copy()
    env.pop("S08_CRASH_AFTER", None)
    if env_overrides:
        env.update(env_overrides)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(PIPELINE_SCRIPT)],
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


def _fetch_offers(conn, table, extra_cols=""):
    cur = conn.cursor()
    cur.execute(f"SELECT offer_id, product_id, seller, price, currency, in_stock{extra_cols} FROM {table}")
    return cur.fetchall(), [d.name for d in cur.description]


def check_converged(include_discount=False):
    """Reused by CP2/CP3. Compares replica.offers (mart) against
    shop.offers (source) row for row. Returns None if they match exactly
    (within PRICE_TOLERANCE on price), otherwise a short description of the
    first few mismatches. When include_discount is True, also compares
    discount_pct."""
    extra = ", discount_pct" if include_discount else ""
    mart_conn = mart_connect()
    source_conn = source_connect()
    try:
        mart_rows, mart_cols = _fetch_offers(mart_conn, "replica.offers", extra)
        source_rows, source_cols = _fetch_offers(source_conn, "shop.offers", extra)
    finally:
        mart_conn.close()
        source_conn.close()

    def _to_dict(rows, cols):
        out = {}
        for row in rows:
            rec = dict(zip(cols, row))
            offer_id = rec.pop("offer_id")
            rec["price"] = float(rec["price"])
            if include_discount and rec.get("discount_pct") is not None:
                rec["discount_pct"] = float(rec["discount_pct"])
            out[offer_id] = rec
        return out

    mart = _to_dict(mart_rows, mart_cols)
    source = _to_dict(source_rows, source_cols)

    mart_ids = set(mart)
    source_ids = set(source)
    missing = sorted(source_ids - mart_ids)
    extra_ids = sorted(mart_ids - source_ids)

    problems = []
    if missing:
        problems.append(f"{len(missing)} offer_id(s) in source but missing from replica.offers, e.g. {missing[:5]}")
    if extra_ids:
        problems.append(f"{len(extra_ids)} offer_id(s) in replica.offers but not in source, e.g. {extra_ids[:5]}")

    mismatches = []
    for offer_id in sorted(mart_ids & source_ids):
        m, s = mart[offer_id], source[offer_id]
        diffs = []
        for field in ("product_id", "seller", "currency", "in_stock"):
            if m[field] != s[field]:
                diffs.append(f"{field}: replica={m[field]!r} source={s[field]!r}")
        if abs(m["price"] - s["price"]) > PRICE_TOLERANCE:
            diffs.append(f"price: replica={m['price']} source={s['price']}")
        if include_discount:
            m_d, s_d = m.get("discount_pct"), s.get("discount_pct")
            if (m_d is None) != (s_d is None) or (m_d is not None and abs(m_d - s_d) > PRICE_TOLERANCE):
                diffs.append(f"discount_pct: replica={m_d!r} source={s_d!r}")
        if diffs:
            mismatches.append(f"offer_id={offer_id} ({'; '.join(diffs)})")
        if len(mismatches) >= 5:
            break
    if mismatches:
        problems.append(f"field mismatches on {len(mismatches)}+ row(s), e.g.: " + " | ".join(mismatches))

    if not problems:
        return None
    return f"replica.offers has {len(mart)} rows, source has {len(source)} rows. " + " ; ".join(problems)


def count_non_tombstone_events(topic=TOPIC, timeout=60.0):
    """Independently drains the whole topic and counts every event whose
    decoded op is not None (i.e. every 'r'/'c'/'u'/'d' -- tombstones don't
    count as an applied change)."""
    n = 0
    for _key, value in drain(topic, from_beginning=True, timeout=timeout):
        payload = decode_value(value)
        op, _before, _after = change_op(payload)
        if op is not None:
            n += 1
    return n


def fetch_applied_changes():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT applied_changes FROM mart.cap_meta WHERE id = 1")
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def full_cleanup():
    teardown_connector()
    drop_result_tables()
    restore_source_schema()
    try:
        subprocess.run(
            ["uv", "run", "python", "generate.py"],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.SubprocessError:
        pass


@guarded
def main():
    if not PIPELINE_SCRIPT.exists():
        not_passed(f"src/pipeline.py not found at {PIPELINE_SCRIPT}")

    teardown_connector()
    drop_result_tables()
    restore_source_schema()
    ensure_source_seeded()

    register_cap_connector()

    r1 = run_pipeline(timeout=FIRST_RUN_TIMEOUT)
    if r1 is None:
        not_passed(f"first pipeline.py run did not idle-exit within {FIRST_RUN_TIMEOUT}s")
    if r1.returncode != 0:
        not_passed(f"first pipeline.py run exited {r1.returncode} -- {_last_line(r1.stderr or r1.stdout)}")

    ops = build_workload(
        seed=WORKLOAD_SEED,
        n_insert=WORKLOAD_N_INSERT,
        n_update=WORKLOAD_N_UPDATE,
        n_delete=WORKLOAD_N_DELETE,
    )
    apply_workload(ops)

    r2 = run_pipeline(timeout=SECOND_RUN_TIMEOUT)
    if r2 is None:
        not_passed(f"second pipeline.py run did not idle-exit within {SECOND_RUN_TIMEOUT}s")
    if r2.returncode != 0:
        not_passed(f"second pipeline.py run exited {r2.returncode} -- {_last_line(r2.stderr or r2.stdout)}")

    problem = check_converged()
    if problem is not None:
        full_cleanup()
        not_passed(f"after burst: {problem}")

    expected_changes = count_non_tombstone_events()
    applied_changes = fetch_applied_changes()
    if applied_changes is None:
        full_cleanup()
        not_passed("mart.cap_meta has no row with id=1 -- was ensure_tables run?")
    if applied_changes != expected_changes:
        full_cleanup()
        direction = "over" if applied_changes > expected_changes else "under"
        hint = " (double-counting?)" if direction == "over" else " (lost updates / dedup too aggressive?)"
        not_passed(
            f"mart.cap_meta.applied_changes={applied_changes}, expected {expected_changes} "
            f"(independently drained non-tombstone event count){hint}"
        )

    full_cleanup()

    passed(
        f"replica.offers converged with shop.offers after snapshot + burst "
        f"({WORKLOAD_N_INSERT} inserts, {WORKLOAD_N_UPDATE} updates, {WORKLOAD_N_DELETE} deletes); "
        f"mart.cap_meta.applied_changes={applied_changes} matches drained non-tombstone count exactly"
    )


if __name__ == "__main__":
    main()
