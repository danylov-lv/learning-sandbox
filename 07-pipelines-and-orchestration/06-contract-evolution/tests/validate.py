"""Validator for task 06 (contract-evolution).

Run from the task directory:

    uv run python tests/validate.py

Checks, across all 14 days (2025-06-01..2025-06-14):
  - core.price_records row counts match ground truth valid_records.
  - per-currency price sums match ground truth per_day_currency within 0.02
    tolerance, including 2025-06-12..14 (proves the locale price parser is
    correct, since ground truth withholds a numeric answer for those days
    directly and this check only passes if the normalizer got it right).
  - seller_rating is populated (non-null) for at least 95% of rows on days
    >= 2025-06-10, and entirely absent (null) on every earlier day.
  - data/alerts/alerts.ndjson has at least one type='contract_drift' alert
    referencing 2025-06-10 and at least one referencing 2025-06-12, each
    with more than just type/dt (a summary field of some kind).
  - src/downstream_check.sql returns at least one row for every one of the
    14 days.
  - ops.quarantine(stage='contract') counts, re-checked across all 14 days
    post-evolution, are consistent with ground truth invalid-record counts
    (i.e. drift-valid rows are not still stuck in quarantine).
"""

import os
import sys
from pathlib import Path

# Fail fast instead of hanging when the warehouse container is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.common import (  # noqa: E402
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
    read_alerts,
)

ALL_DAYS = [f"2025-06-{d:02d}" for d in range(1, 15)]
DRIFT_A_DAY = "2025-06-10"
DRIFT_B_DAY = "2025-06-12"
PRICE_SUM_TOLERANCE = 0.02
SELLER_RATING_MIN_SHARE = 0.95

DOWNSTREAM_CHECK_SQL = (Path(__file__).resolve().parents[1] / "src" / "downstream_check.sql").read_text(
    encoding="utf-8"
)


def check_core_counts_and_sums(conn, gt):
    with conn.cursor() as cur:
        for dt in ALL_DAYS:
            day_gt = gt["per_day"].get(dt)
            if day_gt is None:
                not_passed(f"ground truth has no per_day entry for {dt}")

            cur.execute("SELECT count(*) FROM core.price_records WHERE dt = %s", (dt,))
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
                        f"{PRICE_SUM_TOLERANCE} of ground truth {gt_vals['price_sum']} "
                        "(check your locale price normalizer)"
                    )


def check_seller_rating(conn):
    with conn.cursor() as cur:
        for dt in ALL_DAYS:
            cur.execute(
                "SELECT count(*), count(seller_rating) FROM core.price_records WHERE dt = %s",
                (dt,),
            )
            total, non_null = cur.fetchone()
            if total == 0:
                not_passed(f"{dt}: core.price_records has no rows, cannot check seller_rating")
            if dt < DRIFT_A_DAY:
                if non_null != 0:
                    not_passed(
                        f"{dt}: expected seller_rating entirely null before {DRIFT_A_DAY}, "
                        f"found {non_null}/{total} non-null"
                    )
            else:
                share = non_null / total
                if share < SELLER_RATING_MIN_SHARE:
                    not_passed(
                        f"{dt}: seller_rating populated for only {share:.3f} of rows, "
                        f"expected >= {SELLER_RATING_MIN_SHARE} on/after {DRIFT_A_DAY}"
                    )


def check_quarantine_consistency(conn, gt):
    with conn.cursor() as cur:
        for dt in ALL_DAYS:
            day_gt = gt["per_day"][dt]
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
                    f"below ground truth invalid_records total {invalid_total}"
                )
            if quarantine_count > invalid_total + duplicate_lines:
                not_passed(
                    f"{dt}: quarantine(stage='contract') count {quarantine_count} exceeds "
                    f"the plausible upper bound {invalid_total + duplicate_lines} — looks like "
                    "drift-valid rows are still stuck in quarantine after evolution"
                )


def check_drift_alerts():
    alerts = read_alerts()
    drift_alerts = [a for a in alerts if isinstance(a, dict) and a.get("type") == "contract_drift"]
    if not drift_alerts:
        not_passed("no alert with type='contract_drift' found in data/alerts/alerts.ndjson")

    for label, day in [("drift A (seller_rating)", DRIFT_A_DAY), ("drift B (price string)", DRIFT_B_DAY)]:
        matches = [a for a in drift_alerts if _alert_mentions(a, day)]
        if not matches:
            not_passed(f"no contract_drift alert references {day} ({label})")
        has_summary = any(_has_summary_field(a) for a in matches)
        if not has_summary:
            not_passed(
                f"contract_drift alert(s) referencing {day} have no extra descriptive field "
                "beyond type/dt (expected a short summary of what changed)"
            )


def _alert_mentions(alert, day):
    import json as _json

    return day in _json.dumps(alert)


def _has_summary_field(alert):
    for k, v in alert.items():
        if k in ("type", "dt"):
            continue
        if isinstance(v, str) and len(v.strip()) > 3:
            return True
        if isinstance(v, (dict, list)) and v:
            return True
    return False


def check_downstream(conn):
    with conn.cursor() as cur:
        cur.execute(DOWNSTREAM_CHECK_SQL)
        rows = cur.fetchall()
    if not rows:
        not_passed("downstream_check.sql returned no rows at all")
    seen_days = {str(r[0]) for r in rows}
    missing = [d for d in ALL_DAYS if d not in seen_days]
    if missing:
        not_passed(f"downstream_check.sql missing rows for days: {missing}")


@guarded
def main():
    gt = load_ground_truth()
    conn = pg_connect()
    try:
        check_core_counts_and_sums(conn, gt)
        check_seller_rating(conn)
        check_quarantine_consistency(conn, gt)
        check_downstream(conn)
    finally:
        conn.close()

    check_drift_alerts()

    passed("all 14 days loaded and correct, drift detected and alerted, downstream check intact")


if __name__ == "__main__":
    main()
