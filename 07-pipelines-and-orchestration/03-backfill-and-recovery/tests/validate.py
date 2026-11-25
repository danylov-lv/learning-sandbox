"""Validator for 03-backfill-and-recovery.

Connects to the warehouse over the host port and checks final state only —
it does not invoke the backfill CLI itself. Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, load_ground_truth, not_passed, passed  # noqa: E402

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

DAG_ID = "t02_incremental_load"
REPAIRED_DAYS = {"2025-06-06", "2025-06-07", "2025-06-08"}


@guarded
def main():
    gt = load_ground_truth()
    days = gt["days"]
    if len(days) != 14:
        not_passed(f"ground truth lists {len(days)} days, expected 14")

    import psycopg

    from harness.common import pg_connect

    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            for day in days:
                try:
                    cur.execute(
                        "SELECT count(*), count(distinct line_no) FROM staging.price_records_raw WHERE dt = %s",
                        (day,),
                    )
                except psycopg.errors.UndefinedTable:
                    not_passed(
                        "staging.price_records_raw does not exist — apply src/ddl.sql (task 01) first"
                    )
                row_count, distinct_line_no = cur.fetchone()
                expected = gt["per_day"][day]["parseable_records"]

                if row_count == 0:
                    not_passed(
                        f"staging.price_records_raw has 0 rows for dt={day} — backfill not run yet"
                    )
                if row_count != expected:
                    not_passed(
                        f"staging row count for dt={day} is {row_count}, expected {expected} "
                        "(ground truth parseable_records)"
                    )
                if distinct_line_no != row_count:
                    not_passed(
                        f"line_no is not unique for dt={day}: {distinct_line_no} distinct "
                        f"values over {row_count} rows"
                    )

            for day in days:
                try:
                    cur.execute(
                        "SELECT count(*) FROM ops.load_audit "
                        "WHERE dag_id = %s AND dt = %s AND status = 'success'",
                        (DAG_ID, day),
                    )
                except psycopg.errors.UndefinedTable:
                    not_passed("ops.load_audit does not exist — apply src/ddl.sql (task 01) first")
                success_count = cur.fetchone()[0]

                min_expected = 2 if day in REPAIRED_DAYS else 1
                if success_count < min_expected:
                    not_passed(
                        f"ops.load_audit has {success_count} success row(s) for dag_id={DAG_ID}, "
                        f"dt={day}, expected at least {min_expected} "
                        f"({'repaired day, needs initial backfill + repair' if day in REPAIRED_DAYS else 'needs at least the initial backfill'})"
                    )
    finally:
        conn.close()

    passed(
        "all 14 days present with correct row counts and no line_no duplication; "
        f"audit shows >=2 success runs for {sorted(REPAIRED_DAYS)} and >=1 for the rest"
    )


if __name__ == "__main__":
    main()
