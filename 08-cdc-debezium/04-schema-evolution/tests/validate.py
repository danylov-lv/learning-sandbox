"""Validator for 08-cdc-debezium task 04 -- schema-evolution.

Registers connector s08-t04 on shop.offers, runs the learner's
src/materialize.py to converge the pre-DDL snapshot/stream, then performs a
live ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2) on the
source, drives a deterministic post-DDL insert/update/delete burst (plus
explicit discount_pct writes) through the SAME running connector, and runs
materialize.py again. The second run must not crash (an additive column must
not break a well-written consumer) and replica.offers must converge with
shop.offers exactly, including discount_pct.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import random
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

CONNECTOR_NAME = "s08-t04"
SLOT_NAME = "s08_t04_slot"
PUB_NAME = "s08_t04_pub"
TOPIC_PREFIX = "s08.t04"
MATERIALIZE_SCRIPT = TASK_ROOT / "src" / "materialize.py"

DISCOUNT_SEED = 44
DISCOUNT_SAMPLE_SIZE = 50
DISCOUNT_MIN, DISCOUNT_MAX = 0.0, 35.0
PRICE_TOLERANCE = 0.01
DISCOUNT_TOLERANCE = 0.01

RUN_TIMEOUT = 180
STREAM_SETTLE_SECONDS = 8
SLOT_DROP_ATTEMPTS = 6
SLOT_DROP_DELAY = 2.0


def _drop_slot_retrying(conn, name):
    """drop_slot() can raise ObjectInUse for a few seconds right after
    delete_connector() -- the Debezium task's replication connection hasn't
    closed yet (documented gotcha, see .authoring/design.md). Retry a few
    times instead of failing the whole run on that timing window."""
    import psycopg

    for attempt in range(SLOT_DROP_ATTEMPTS):
        try:
            return drop_slot(conn, name)
        except psycopg.errors.ObjectInUse:
            conn.rollback()
            if attempt == SLOT_DROP_ATTEMPTS - 1:
                raise
            time.sleep(SLOT_DROP_DELAY)


def _teardown():
    delete_connector(CONNECTOR_NAME)
    conn = source_connect()
    try:
        _drop_slot_retrying(conn, SLOT_NAME)
        drop_publication(conn, PUB_NAME)
    finally:
        conn.close()
    reset_topics(TOPIC_PREFIX + ".")
    mconn = mart_connect()
    try:
        cur = mconn.cursor()
        cur.execute("DROP TABLE IF EXISTS replica.offers")
        mconn.commit()
    finally:
        mconn.close()


def _reset_source_schema(conn):
    """Defensive guard: a previous, interrupted run of THIS validator (or a
    stale manual experiment) may have left discount_pct on the source. Start
    every run from the stock pre-migration schema."""
    cur = conn.cursor()
    cur.execute("ALTER TABLE shop.offers DROP COLUMN IF EXISTS discount_pct")
    conn.commit()


def _ensure_seeded(conn, n_offers_expected):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM shop.offers")
    n = cur.fetchone()[0]
    if n != n_offers_expected:
        not_passed(
            f"shop.offers has {n} rows, expected {n_offers_expected} from ground truth -- "
            "run `uv run python generate.py` first"
        )


def _register():
    cfg = debezium_pg_connector_config(
        CONNECTOR_NAME, TOPIC_PREFIX, SLOT_NAME, PUB_NAME, "shop.offers",
        extra={"decimal.handling.mode": "double"},
    )
    register_connector(cfg)
    wait_for_connector_running(CONNECTOR_NAME)


def _run_materialize():
    env = os.environ.copy()
    try:
        return subprocess.run(
            ["uv", "run", "python", str(MATERIALIZE_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def _apply_post_ddl_workload(conn):
    """Deterministic burst (seed=4) plus deterministic discount_pct writes
    on both the freshly-inserted rows and a fixed sample of pre-existing
    ones -- all AFTER the ALTER TABLE, so materialize.py must merge
    pre-DDL and post-DDL after-images on the same primary key correctly."""
    ops = build_workload(seed=4, n_insert=300, n_update=600, n_delete=100)
    cur = conn.cursor()
    insert_discount_rng = random.Random(DISCOUNT_SEED)
    for op in ops:
        if op["op"] == "update":
            cur.execute(
                "UPDATE shop.offers SET price=%s, in_stock=%s WHERE offer_id=%s",
                (op["price"], op["in_stock"], op["offer_id"]),
            )
        elif op["op"] == "delete":
            cur.execute("DELETE FROM shop.offers WHERE offer_id=%s", (op["offer_id"],))
        elif op["op"] == "insert":
            discount = round(insert_discount_rng.uniform(DISCOUNT_MIN, DISCOUNT_MAX), 2)
            cur.execute(
                "INSERT INTO shop.offers "
                "(offer_id, product_id, seller, price, currency, in_stock, discount_pct) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (op["offer_id"], op["product_id"], op["seller"], op["price"],
                 op["currency"], op["in_stock"], discount),
            )
    conn.commit()


def _set_discount_on_fixed_ids(conn, n_offers):
    """A fixed, deterministic sample of pre-existing offer_ids gets an
    explicit discount_pct UPDATE, independent of the insert/update/delete
    burst above (a no-op if a sampled id happens to have just been
    deleted, which is fine -- 0 rows affected)."""
    rng = random.Random(DISCOUNT_SEED + 1)
    ids = sorted(rng.sample(range(1, n_offers + 1), DISCOUNT_SAMPLE_SIZE))
    cur = conn.cursor()
    for offer_id in ids:
        value = round(rng.uniform(DISCOUNT_MIN, DISCOUNT_MAX), 2)
        cur.execute("UPDATE shop.offers SET discount_pct=%s WHERE offer_id=%s", (value, offer_id))
    conn.commit()
    return ids


def _read_source(conn, with_discount):
    cols = "offer_id, product_id, seller, price, currency, in_stock"
    if with_discount:
        cols += ", discount_pct"
    cur = conn.cursor()
    cur.execute(f"SELECT {cols} FROM shop.offers")
    rows = {}
    for row in cur.fetchall():
        offer_id = row[0]
        entry = {
            "product_id": row[1], "seller": row[2], "price": float(row[3]),
            "currency": row[4], "in_stock": row[5],
        }
        if with_discount:
            entry["discount_pct"] = None if row[6] is None else float(row[6])
        rows[offer_id] = entry
    return rows


def _read_replica(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT offer_id, product_id, seller, price, currency, in_stock, discount_pct "
        "FROM replica.offers"
    )
    rows = {}
    for offer_id, product_id, seller, price, currency, in_stock, discount_pct in cur.fetchall():
        rows[offer_id] = {
            "product_id": product_id, "seller": seller,
            "price": None if price is None else float(price),
            "currency": currency, "in_stock": in_stock,
            "discount_pct": None if discount_pct is None else float(discount_pct),
        }
    return rows


def _assert_converged(source_rows, replica_rows, check_discount):
    missing = sorted(set(source_rows) - set(replica_rows))
    extra = sorted(set(replica_rows) - set(source_rows))
    if missing:
        not_passed(
            f"replica.offers is missing {len(missing)} offer_id(s) present in source, "
            f"e.g. {missing[:5]}"
        )
    if extra:
        not_passed(
            f"replica.offers has {len(extra)} extra offer_id(s) not in source, "
            f"e.g. {extra[:5]} -- deletes not applied?"
        )

    for offer_id, s in source_rows.items():
        r = replica_rows[offer_id]
        if (r["product_id"], r["seller"], r["currency"], r["in_stock"]) != (
            s["product_id"], s["seller"], s["currency"], s["in_stock"]
        ):
            not_passed(f"offer_id {offer_id} mismatched fields: source={s}, replica={r}")
        if r["price"] is None or abs(r["price"] - s["price"]) > PRICE_TOLERANCE:
            not_passed(f"offer_id {offer_id} price mismatch: source={s['price']}, replica={r['price']}")
        if check_discount:
            s_disc, r_disc = s["discount_pct"], r["discount_pct"]
            if (s_disc is None) != (r_disc is None):
                not_passed(
                    f"offer_id {offer_id} discount_pct null-mismatch: "
                    f"source={s_disc}, replica={r_disc}"
                )
            if s_disc is not None and abs(r_disc - s_disc) > DISCOUNT_TOLERANCE:
                not_passed(
                    f"offer_id {offer_id} discount_pct mismatch: "
                    f"source={s_disc}, replica={r_disc}"
                )


def _reseed():
    subprocess.run(
        ["uv", "run", "python", "generate.py"],
        cwd=str(MODULE_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _final_cleanup():
    """Runs no matter how main() exits (pass, NOT PASSED, or crash) so a
    failed run never leaves an orphaned connector/slot pinning WAL on the
    source, a discount_pct column lingering on shop.offers, or a mutated
    source left behind for the next task."""
    try:
        conn = source_connect()
        try:
            _reset_source_schema(conn)
        finally:
            conn.close()
    except Exception as e:
        print(f"WARNING: source schema reset failed: {e}", file=sys.stderr)

    try:
        _teardown()
    except Exception as e:
        print(f"WARNING: connector/topic/replica cleanup failed: {e}", file=sys.stderr)

    try:
        _reseed()
    except Exception as e:
        print(f"WARNING: source reseed failed during cleanup: {e}", file=sys.stderr)


@guarded
def main():
    gt = load_ground_truth()
    n_offers = gt["n_offers"]

    if not MATERIALIZE_SCRIPT.exists():
        not_passed(f"src/materialize.py not found at {MATERIALIZE_SCRIPT}")

    # 1. clean slate.
    _teardown()

    try:
        # 2. source-schema guard + seeded check.
        conn = source_connect()
        try:
            _reset_source_schema(conn)
            _ensure_seeded(conn, n_offers)
        finally:
            conn.close()

        # 3. register the connector, wait for RUNNING (snapshot underway/done).
        _register()

        # 4. converge the pre-DDL snapshot/stream.
        r1 = _run_materialize()
        if r1 is None:
            not_passed(f"initial materialize.py run did not exit within {RUN_TIMEOUT}s")
        if r1.returncode != 0:
            tail = (r1.stdout or "")[-1500:] + (r1.stderr or "")[-1500:]
            not_passed(f"initial materialize.py run exited {r1.returncode} -- output tail:\n{tail}")

        conn = source_connect()
        mconn = mart_connect()
        try:
            source_rows = _read_source(conn, with_discount=False)
            replica_rows_full = _read_replica(mconn)
        finally:
            conn.close()
            mconn.close()
        replica_rows = {oid: {k: v for k, v in row.items() if k != "discount_pct"}
                         for oid, row in replica_rows_full.items()}
        _assert_converged(source_rows, replica_rows, check_discount=False)
        nonnull_early = [oid for oid, row in replica_rows_full.items() if row["discount_pct"] is not None]
        if nonnull_early:
            not_passed(
                f"replica.offers has non-NULL discount_pct BEFORE the source ADD COLUMN for "
                f"offer_id(s) {nonnull_early[:5]} -- should still be NULL at this point"
            )

        # 5. schema evolution: additive ALTER, then a deterministic post-DDL burst.
        conn = source_connect()
        try:
            cur = conn.cursor()
            cur.execute("ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2)")
            conn.commit()
            _apply_post_ddl_workload(conn)
            discount_ids = _set_discount_on_fixed_ids(conn, n_offers)
        finally:
            conn.close()

        time.sleep(STREAM_SETTLE_SECONDS)

        # 6. materialize.py must survive the ADD COLUMN -- no crash, exit 0.
        r2 = _run_materialize()
        if r2 is None:
            not_passed(
                f"post-DDL materialize.py run did not exit within {RUN_TIMEOUT}s -- did it hang "
                "on an after-image that includes the new column?"
            )
        if r2.returncode != 0:
            tail = (r2.stdout or "")[-1500:] + (r2.stderr or "")[-1500:]
            not_passed(
                f"post-DDL materialize.py run exited {r2.returncode} -- an additive ADD COLUMN "
                f"must not crash a well-written consumer. output tail:\n{tail}"
            )

        # 7. exact convergence, including discount_pct.
        conn = source_connect()
        mconn = mart_connect()
        try:
            source_rows = _read_source(conn, with_discount=True)
            replica_rows = _read_replica(mconn)
        finally:
            conn.close()
            mconn.close()
        _assert_converged(source_rows, replica_rows, check_discount=True)

        passed(
            f"replica.offers converged with shop.offers ({len(source_rows)} rows) across an "
            f"ADD COLUMN discount_pct, including {len(discount_ids)} explicitly discounted "
            "pre-existing offers and 300 newly inserted ones"
        )
    finally:
        _final_cleanup()


if __name__ == "__main__":
    main()
