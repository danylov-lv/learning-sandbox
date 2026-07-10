"""Validator for task 05 (contract-gate-pandera).

Run from the task directory:

    uv run python tests/validate.py

Checks, for days 2025-06-01..2025-06-05:
  - core.price_records row count per day matches ground truth valid_records.
  - per-currency price sums in core match ground truth per_day_currency
    within 0.02 tolerance.
  - ops.quarantine(stage='contract') per-day counts are consistent with
    ground truth invalid-record counts (a duplicate line can also be a
    duplicate of an invalid line, so an exact match isn't guaranteed — the
    count must be at least the invalid total and bounded above by invalid
    total + that day's duplicate_lines).
  - rerunning the gate for one already-loaded day leaves core and quarantine
    counts unchanged (idempotency).
"""

import os
import subprocess
import sys
from pathlib import Path

# Fail fast instead of hanging when the warehouse container is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.common import (  # noqa: E402
    MODULE_ROOT,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
)

DAYS = [
    "2025-06-01",
    "2025-06-02",
    "2025-06-03",
    "2025-06-04",
    "2025-06-05",
]

PRICE_SUM_TOLERANCE = 0.02
RERUN_DAY = "2025-06-03"


def check_core_and_quarantine(conn, gt):
    with conn.cursor() as cur:
        for dt in DAYS:
            day_gt = gt["per_day"].get(dt)
            if day_gt is None:
                not_passed(f"ground truth has no per_day entry for {dt}")

            cur.execute(
                "SELECT count(*) FROM core.price_records WHERE dt = %s", (dt,)
            )
            core_count = cur.fetchone()[0]
            expected_count = day_gt["valid_records"]
            if core_count != expected_count:
                not_passed(
                    f"{dt}: core.price_records count {core_count} != "
                    f"ground truth valid_records {expected_count}"
                )

            cur.execute(
                "SELECT currency, count(*), sum(price) FROM core.price_records "
                "WHERE dt = %s GROUP BY currency",
                (dt,),
            )
            rows = {r[0]: (r[1], float(r[2]) if r[2] is not None else 0.0) for r in cur.fetchall()}
            gt_currency = gt["per_day_currency"].get(dt, {})
            for currency, gt_vals in gt_currency.items():
                got_count, got_sum = rows.get(currency, (0, 0.0))
                if got_count != gt_vals["count"]:
                    not_passed(
                        f"{dt}/{currency}: core count {got_count} != "
                        f"ground truth count {gt_vals['count']}"
                    )
                if abs(got_sum - gt_vals["price_sum"]) > PRICE_SUM_TOLERANCE:
                    not_passed(
                        f"{dt}/{currency}: core price sum {got_sum} not within "
                        f"{PRICE_SUM_TOLERANCE} of ground truth {gt_vals['price_sum']}"
                    )

            cur.execute(
                "SELECT count(*) FROM ops.quarantine WHERE dt = %s AND stage = 'contract'",
                (dt,),
            )
            quarantine_count = cur.fetchone()[0]
            invalid_total = day_gt["invalid_records"]["total"]
            duplicate_lines = day_gt["duplicate_lines"]
            if quarantine_count < invalid_total:
                not_passed(
                    f"{dt}: quarantine(stage='contract') count {quarantine_count} is "
                    f"below ground truth invalid_records total {invalid_total} "
                    "(some invalid records were not quarantined)"
                )
            if quarantine_count > invalid_total + duplicate_lines:
                not_passed(
                    f"{dt}: quarantine(stage='contract') count {quarantine_count} exceeds "
                    f"the plausible upper bound {invalid_total + duplicate_lines} "
                    "(invalid_records total + that day's duplicate_lines)"
                )


def snapshot_counts(conn, dt):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.price_records WHERE dt = %s", (dt,))
        core_count = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM ops.quarantine WHERE dt = %s AND stage = 'contract'",
            (dt,),
        )
        quarantine_count = cur.fetchone()[0]
    return core_count, quarantine_count


def check_rerun_idempotency(conn):
    before = snapshot_counts(conn, RERUN_DAY)

    try:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "airflow-scheduler",
                "airflow", "dags", "test", "t05_contract_gate", RERUN_DAY,
            ],
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        not_passed(f"could not run rerun check via docker compose: {e}")

    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-20:] + result.stderr.splitlines()[-20:])
        not_passed(f"rerun of t05_contract_gate for {RERUN_DAY} failed:\n{tail}")

    after = snapshot_counts(conn, RERUN_DAY)
    if before != after:
        not_passed(
            f"rerunning t05_contract_gate for {RERUN_DAY} changed counts: "
            f"before={before} after={after} (core_count, quarantine_count) — the gate is not idempotent"
        )


@guarded
def main():
    gt = load_ground_truth()
    conn = pg_connect()
    try:
        check_core_and_quarantine(conn, gt)
        check_rerun_idempotency(conn)
    finally:
        conn.close()

    passed("core and quarantine counts match ground truth for 2025-06-01..05, gate is idempotent on rerun")


if __name__ == "__main__":
    main()
