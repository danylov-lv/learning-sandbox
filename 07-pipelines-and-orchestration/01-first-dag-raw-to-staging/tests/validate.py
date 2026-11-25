"""Validator for 01-first-dag-raw-to-staging.

Connects to the warehouse over the host port (54306 by default) — no docker
exec needed, this checks the state your DAG run left behind. Run from this
task's directory:

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

TARGET_DAY = "2025-06-01"


@guarded
def main():
    gt = load_ground_truth()
    if TARGET_DAY not in gt["per_day"]:
        not_passed(f"ground truth has no entry for {TARGET_DAY}")
    day_gt = gt["per_day"][TARGET_DAY]

    import psycopg

    from harness.common import pg_connect

    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT count(*), count(distinct line_no), count(payload) "
                    "FROM staging.price_records_raw WHERE dt = %s",
                    (TARGET_DAY,),
                )
            except psycopg.errors.UndefinedTable:
                not_passed(
                    "staging.price_records_raw does not exist — apply src/ddl.sql against the warehouse first"
                )
            row = cur.fetchone()
    finally:
        conn.close()

    row_count, distinct_line_no, non_null_payload = row

    if row_count == 0:
        not_passed(
            f"staging.price_records_raw has 0 rows for dt={TARGET_DAY} — "
            f"run `airflow dags test t01_raw_to_staging {TARGET_DAY}` first"
        )

    expected_rows = day_gt["parseable_records"]
    if row_count != expected_rows:
        not_passed(
            f"staging.price_records_raw has {row_count} rows for dt={TARGET_DAY}, "
            f"expected {expected_rows} (ground truth parseable_records = "
            f"duplicate_lines + valid_records + invalid_records, i.e. total_lines - malformed_lines)"
        )

    if distinct_line_no != row_count:
        not_passed(
            f"line_no is not unique for dt={TARGET_DAY}: {distinct_line_no} distinct values "
            f"over {row_count} rows"
        )

    if non_null_payload != row_count:
        not_passed(
            f"{row_count - non_null_payload} row(s) for dt={TARGET_DAY} have a null payload"
        )

    total_lines = day_gt["total_lines"]
    malformed_lines = day_gt["malformed_lines"]
    skipped = total_lines - row_count
    if skipped != malformed_lines:
        not_passed(
            f"total_lines ({total_lines}) minus rows loaded ({row_count}) = {skipped}, "
            f"expected exactly malformed_lines ({malformed_lines}) to have been skipped — "
            "some non-malformed line was dropped, or a malformed line landed in staging"
        )

    passed(
        f"dt={TARGET_DAY}: {row_count} rows loaded, line_no unique, payload non-null, "
        f"{skipped} malformed lines correctly skipped"
    )


if __name__ == "__main__":
    main()
