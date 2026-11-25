"""Validator for 02-incremental-idempotent-loads.

Connects to the warehouse over the host port, then self-triggers one more
DAG run via `docker compose exec` (from the module directory) as the actual
idempotency proof. Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, load_ground_truth, not_passed, passed  # noqa: E402

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

TARGET_DAY = "2025-06-03"
DAG_ID = "t02_incremental_load"


def _staging_state(cur):
    cur.execute(
        "SELECT count(*), count(distinct line_no) FROM staging.price_records_raw WHERE dt = %s",
        (TARGET_DAY,),
    )
    return cur.fetchone()


def _audit_count(cur):
    cur.execute(
        "SELECT count(*) FROM ops.load_audit WHERE dag_id = %s AND dt = %s",
        (DAG_ID, TARGET_DAY),
    )
    return cur.fetchone()[0]


def _audit_success_count(cur):
    cur.execute(
        "SELECT count(*) FROM ops.load_audit WHERE dag_id = %s AND dt = %s AND status = 'success'",
        (DAG_ID, TARGET_DAY),
    )
    return cur.fetchone()[0]


@guarded
def main():
    gt = load_ground_truth()
    if TARGET_DAY not in gt["per_day"]:
        not_passed(f"ground truth has no entry for {TARGET_DAY}")
    expected_rows = gt["per_day"][TARGET_DAY]["parseable_records"]

    import psycopg

    from harness.common import pg_connect

    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            try:
                before_count, before_distinct = _staging_state(cur)
            except psycopg.errors.UndefinedTable:
                not_passed(
                    "staging.price_records_raw does not exist — apply src/ddl.sql and load first"
                )
            try:
                before_audit = _audit_count(cur)
                before_success = _audit_success_count(cur)
            except psycopg.errors.UndefinedTable:
                not_passed("ops.load_audit does not exist — apply src/ddl.sql first")
    finally:
        conn.close()

    if before_count == 0:
        not_passed(
            f"staging.price_records_raw has 0 rows for dt={TARGET_DAY} — "
            f"run `airflow dags test {DAG_ID} {TARGET_DAY}` first"
        )
    if before_audit == 0:
        not_passed(
            f"ops.load_audit has no rows for dag_id={DAG_ID}, dt={TARGET_DAY} — "
            "load_partition must write one audit row per run"
        )

    # --- self-triggered rerun: the actual idempotency proof ---
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "airflow-scheduler",
                "airflow",
                "dags",
                "test",
                DAG_ID,
                TARGET_DAY,
            ],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        not_passed("docker not found on PATH — is Docker installed and available?")
    except subprocess.TimeoutExpired:
        not_passed("self-triggered rerun of the DAG timed out after 300s")

    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        not_passed(
            f"self-triggered rerun `docker compose exec ... airflow dags test {DAG_ID} {TARGET_DAY}` "
            f"exited {result.returncode} — output tail:\n{tail}"
        )

    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            after_count, after_distinct = _staging_state(cur)
            after_audit = _audit_count(cur)
            after_success = _audit_success_count(cur)
    finally:
        conn.close()

    if after_count != before_count:
        not_passed(
            f"staging row count for dt={TARGET_DAY} changed after rerun: "
            f"{before_count} -> {after_count} (should be unchanged)"
        )
    if after_count != expected_rows:
        not_passed(
            f"staging row count for dt={TARGET_DAY} is {after_count}, "
            f"expected {expected_rows} (ground truth parseable_records)"
        )
    if after_distinct != after_count:
        not_passed(
            f"line_no is not unique for dt={TARGET_DAY} after rerun: "
            f"{after_distinct} distinct values over {after_count} rows"
        )
    if after_audit != before_audit + 1:
        not_passed(
            f"ops.load_audit row count for dag_id={DAG_ID}, dt={TARGET_DAY} went from "
            f"{before_audit} to {after_audit} across the rerun — expected exactly +1"
        )
    if after_success != before_success + 1:
        not_passed(
            f"ops.load_audit success-row count for dag_id={DAG_ID}, dt={TARGET_DAY} went from "
            f"{before_success} to {after_success} across the rerun — expected exactly +1 with "
            "status='success'"
        )

    passed(
        f"dt={TARGET_DAY}: rerun left staging at {after_count} rows (unchanged, matches ground "
        f"truth), no line_no duplication, audit gained exactly one success row"
    )


if __name__ == "__main__":
    main()
