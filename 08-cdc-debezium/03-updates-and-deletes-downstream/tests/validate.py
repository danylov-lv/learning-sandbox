"""Validator for 08-cdc-debezium task 03 -- updates-and-deletes-downstream.

Registers this task's own Debezium connector (decimal.handling.mode=double,
so the learner's consumer sees plain-number prices), runs the learner's
materialize.py against the initial snapshot, checks replica.offers ==
shop.offers exactly, then applies a deterministic insert/update/delete
burst to the source, runs materialize.py again as a resume, and checks
convergence again.

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
    reset_topics,
    source_connect,
    wait_for_connector_running,
)
from generate import build_workload  # noqa: E402

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

CONNECTOR_NAME = "s08-t03"
SLOT_NAME = "s08_t03_slot"
PUBLICATION_NAME = "s08_t03_pub"
TOPIC_PREFIX = "s08.t03"

MATERIALIZE_SCRIPT = TASK_ROOT / "src" / "materialize.py"
FIRST_RUN_TIMEOUT = 300
SECOND_RUN_TIMEOUT = 300
CONNECTOR_RUNNING_TIMEOUT = 60

PRICE_TOLERANCE = 0.01

WORKLOAD_SEED = 3
WORKLOAD_N_INSERT = 500
WORKLOAD_N_UPDATE = 1000
WORKLOAD_N_DELETE = 300


def _teardown_connector():
    delete_connector(CONNECTOR_NAME)
    conn = source_connect()
    try:
        # The slot can stay briefly "active" right after connector deletion
        # (see .authoring/notes-infra.md) -- retry once after a short wait.
        try:
            drop_slot(conn, SLOT_NAME)
        except Exception:
            time.sleep(5)
            drop_slot(conn, SLOT_NAME)
        drop_publication(conn, PUBLICATION_NAME)
    finally:
        conn.close()
    reset_topics(TOPIC_PREFIX)


def _drop_replica_table():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS replica.offers")
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


def _ensure_source_seeded():
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


def _apply_workload(ops):
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


def _run_materialize(timeout):
    env = os.environ.copy()
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


def _fetch_offers(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT offer_id, product_id, seller, price, currency, in_stock FROM {table}")
    rows = {}
    for offer_id, product_id, seller, price, currency, in_stock in cur.fetchall():
        rows[offer_id] = {
            "product_id": product_id,
            "seller": seller,
            "price": float(price),
            "currency": currency,
            "in_stock": in_stock,
        }
    return rows


def diff_offers(mart_conn, source_conn):
    """Compare replica.offers (mart) against shop.offers (source). Returns
    None if they match exactly (within PRICE_TOLERANCE on price), otherwise
    a short human-readable description of the first few mismatches."""
    mart_rows = _fetch_offers(mart_conn, "replica.offers")
    source_rows = _fetch_offers(source_conn, "shop.offers")

    mart_ids = set(mart_rows)
    source_ids = set(source_rows)
    missing = sorted(source_ids - mart_ids)
    extra = sorted(mart_ids - source_ids)

    problems = []
    if missing:
        problems.append(f"{len(missing)} offer_id(s) in source but missing from replica.offers, e.g. {missing[:5]}")
    if extra:
        problems.append(f"{len(extra)} offer_id(s) in replica.offers but not in source, e.g. {extra[:5]}")

    mismatches = []
    for offer_id in sorted(mart_ids & source_ids):
        m = mart_rows[offer_id]
        s = source_rows[offer_id]
        diffs = []
        for field in ("product_id", "seller", "currency", "in_stock"):
            if m[field] != s[field]:
                diffs.append(f"{field}: replica={m[field]!r} source={s[field]!r}")
        if abs(m["price"] - s["price"]) > PRICE_TOLERANCE:
            diffs.append(f"price: replica={m['price']} source={s['price']}")
        if diffs:
            mismatches.append(f"offer_id={offer_id} ({'; '.join(diffs)})")
        if len(mismatches) >= 5:
            break
    if mismatches:
        problems.append(f"field mismatches on {len(mismatches)}+ row(s), e.g.: " + " | ".join(mismatches))

    if not problems:
        return None
    return f"replica.offers has {len(mart_rows)} rows, source has {len(source_rows)} rows. " + " ; ".join(problems)


def _final_cleanup():
    """Runs no matter how main() exits (pass, NOT PASSED, or crash) so a
    failed run never leaves an orphaned connector/slot pinning WAL on the
    source, or a mutated source left behind for the next task."""
    try:
        _teardown_connector()
    except Exception as e:
        print(f"WARNING: connector/topic cleanup failed: {e}", file=sys.stderr)

    try:
        _drop_replica_table()
    except Exception as e:
        print(f"WARNING: replica table cleanup failed: {e}", file=sys.stderr)

    try:
        reseed = subprocess.run(
            ["uv", "run", "python", "generate.py"],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if reseed.returncode != 0:
            tail = (reseed.stdout or "")[-1500:] + (reseed.stderr or "")[-1500:]
            print(f"WARNING: source reseed failed during cleanup: {tail}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: source reseed failed during cleanup: {e}", file=sys.stderr)


@guarded
def main():
    if not MATERIALIZE_SCRIPT.exists():
        not_passed(f"src/materialize.py not found at {MATERIALIZE_SCRIPT}")

    # --- clean slate
    _teardown_connector()
    _drop_replica_table()

    try:
        _ensure_source_seeded()

        # --- register connector, wait for it to come up (snapshot phase begins)
        connector_def = debezium_pg_connector_config(
            CONNECTOR_NAME, TOPIC_PREFIX, SLOT_NAME, PUBLICATION_NAME, "shop.offers",
            extra={"decimal.handling.mode": "double"},
        )
        register_connector(connector_def)
        wait_for_connector_running(CONNECTOR_NAME, timeout=CONNECTOR_RUNNING_TIMEOUT)

        # --- first run: consume the snapshot, converge with the initial source state
        r1 = _run_materialize(FIRST_RUN_TIMEOUT)
        if r1 is None:
            not_passed(f"first materialize.py run did not idle-exit within {FIRST_RUN_TIMEOUT}s")
        if r1.returncode != 0:
            tail = (r1.stdout or "")[-1500:] + (r1.stderr or "")[-1500:]
            not_passed(f"first materialize.py run exited {r1.returncode} -- output tail:\n{tail}")

        mart_conn = mart_connect()
        source_conn = source_connect()
        try:
            problem = diff_offers(mart_conn, source_conn)
        finally:
            mart_conn.close()
            source_conn.close()
        if problem is not None:
            not_passed(f"after initial snapshot: {problem}")

        # --- burst: inserts, updates, deletes against the source
        ops = build_workload(
            seed=WORKLOAD_SEED,
            n_insert=WORKLOAD_N_INSERT,
            n_update=WORKLOAD_N_UPDATE,
            n_delete=WORKLOAD_N_DELETE,
        )
        _apply_workload(ops)

        # --- second run: resume, catch up with the streamed burst
        r2 = _run_materialize(SECOND_RUN_TIMEOUT)
        if r2 is None:
            not_passed(f"second materialize.py run did not idle-exit within {SECOND_RUN_TIMEOUT}s")
        if r2.returncode != 0:
            tail = (r2.stdout or "")[-1500:] + (r2.stderr or "")[-1500:]
            not_passed(f"second materialize.py run exited {r2.returncode} -- output tail:\n{tail}")

        mart_conn = mart_connect()
        source_conn = source_connect()
        try:
            problem = diff_offers(mart_conn, source_conn)
            n_rows = len(_fetch_offers(mart_conn, "replica.offers"))
        finally:
            mart_conn.close()
            source_conn.close()
        if problem is not None:
            not_passed(f"after insert/update/delete burst: {problem}")

        passed(
            f"replica.offers converged with shop.offers ({n_rows} rows) both after the initial "
            f"snapshot and after a burst of {WORKLOAD_N_INSERT} inserts, {WORKLOAD_N_UPDATE} "
            f"updates, and {WORKLOAD_N_DELETE} deletes"
        )
    finally:
        _final_cleanup()


if __name__ == "__main__":
    main()
