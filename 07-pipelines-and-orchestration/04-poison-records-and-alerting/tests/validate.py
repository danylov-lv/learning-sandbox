"""Validator for 04-poison-records-and-alerting.

Run from the task directory:

    uv run python tests/validate.py

Expects (see README's Completion criteria):
  - ddl.sql applied, DAG copied to dags/, drill day generated,
  - a clean alerts file produced by exactly the three scenario runs
    (2025-06-05, 2025-06-15, 2025-06-16) in any order,
  - docker compose stack up (the validator reruns 2025-06-05 itself to
    prove idempotency).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _reference import classify_file  # noqa: E402
from harness import common  # noqa: E402
from harness.common import guarded, not_passed, passed  # noqa: E402

BASE_DAY = "2025-06-05"
DRILL_DAY = "2025-06-15"
MISSING_DAY = "2025-06-16"
DAG_ID = "t04_quarantine_and_alerts"

REASONS = ["missing_product_url", "invalid_price", "unknown_currency", "invalid_scraped_at"]
GT_REASON_KEYS = {
    "missing_product_url": "missing_url",
    "invalid_price": "bad_price",
    "unknown_currency": "unknown_currency",
    "invalid_scraped_at": "bad_timestamp",
}
RATE_THRESHOLD = 0.03


def day_counts(conn, dt):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM staging.price_records_raw WHERE dt = %s", (dt,))
        staging = cur.fetchone()[0]
        cur.execute(
            "SELECT stage, reason, count(*) FROM ops.quarantine WHERE dt = %s GROUP BY stage, reason",
            (dt,),
        )
        quarantine = {(stage, reason): n for stage, reason, n in cur.fetchall()}
    return staging, quarantine


def check_day(label, dt, staging, quarantine, ref):
    got_malformed = quarantine.get(("ingest", "malformed"), 0)
    if got_malformed != ref["malformed"]:
        not_passed(
            f"{label}: ops.quarantine stage='ingest' reason='malformed' has "
            f"{got_malformed} rows for dt={dt}, expected {ref['malformed']}"
        )
    for reason in REASONS:
        expected = ref["invalid_by_reason"][reason]
        got = quarantine.get(("validate", reason), 0)
        if got != expected:
            not_passed(
                f"{label}: ops.quarantine stage='validate' reason='{reason}' has "
                f"{got} rows for dt={dt}, expected {expected}"
            )
    unexpected = [k for k in quarantine if k not in {("ingest", "malformed")} | {("validate", r) for r in REASONS}]
    if unexpected:
        not_passed(f"{label}: unexpected (stage, reason) pairs in ops.quarantine for dt={dt}: {unexpected}")
    if staging != ref["valid"]:
        not_passed(
            f"{label}: staging.price_records_raw has {staging} rows for dt={dt}, "
            f"expected {ref['valid']} (every line that is neither malformed nor invalid, duplicates included)"
        )


def rerun_dag(dt):
    cmd = [
        "docker", "compose", "exec", "-T", "airflow-scheduler",
        "airflow", "dags", "test", DAG_ID, dt,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=common.MODULE_ROOT, capture_output=True, text=True, timeout=900,
        )
    except FileNotFoundError:
        not_passed("docker not found on PATH — cannot rerun the DAG for the idempotency check")
    except subprocess.TimeoutExpired:
        not_passed(f"`airflow dags test {DAG_ID} {dt}` timed out after 900s")
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
        not_passed(
            f"validator rerun of `airflow dags test {DAG_ID} {dt}` failed "
            f"(is the compose stack up and the DAG copied to dags/?): {' | '.join(tail)}"
        )


@guarded
def main():
    gt = common.load_ground_truth()
    if BASE_DAY not in gt["per_day"]:
        not_passed(f"{BASE_DAY} missing from ground-truth.json — regenerate data")
    gt_day = gt["per_day"][BASE_DAY]

    base_file = common.raw_day_file(BASE_DAY)
    if not base_file.exists():
        not_passed(f"raw file missing: {base_file} — run `uv run python generate.py` from the module root")
    drill_file = common.raw_day_file(DRILL_DAY)
    if not drill_file.exists():
        not_passed(f"drill day missing: {drill_file} — run `uv run python tests/make_drill_day.py` first")
    if common.raw_day_dir(MISSING_DAY).exists():
        not_passed(f"{common.raw_day_dir(MISSING_DAY)} exists — {MISSING_DAY} must have no data so the DAG run fails")

    ref_base = classify_file(base_file, BASE_DAY)
    if ref_base["total_lines"] != gt_day["total_lines"] or ref_base["malformed"] != gt_day["malformed_lines"]:
        not_passed(
            f"raw file for {BASE_DAY} disagrees with ground-truth.json "
            f"(lines {ref_base['total_lines']} vs {gt_day['total_lines']}, "
            f"malformed {ref_base['malformed']} vs {gt_day['malformed_lines']}) — regenerate data"
        )
    for reason, gt_key in GT_REASON_KEYS.items():
        delta = ref_base["invalid_by_reason"][reason] - gt_day["invalid_records"][gt_key]
        if not (0 <= delta <= gt_day["duplicate_lines"]):
            not_passed(f"reference classifier disagrees with ground truth for reason '{reason}' — regenerate data")
    ref_drill = classify_file(drill_file, DRILL_DAY)

    conn = common.pg_connect()
    with conn:
        staging_base, quar_base = day_counts(conn, BASE_DAY)
        if staging_base == 0 and not quar_base:
            not_passed(f"no rows for dt={BASE_DAY} in staging or ops.quarantine — run the DAG on {BASE_DAY} first")
        check_day("base day", BASE_DAY, staging_base, quar_base, ref_base)

        staging_drill, quar_drill = day_counts(conn, DRILL_DAY)
        if staging_drill == 0 and not quar_drill:
            not_passed(f"no rows for dt={DRILL_DAY} — run the DAG on the drill day")
        check_day("drill day", DRILL_DAY, staging_drill, quar_drill, ref_drill)

        rerun_dag(BASE_DAY)

        staging_after, quar_after = day_counts(conn, BASE_DAY)
        if staging_after != staging_base or quar_after != quar_base:
            not_passed(
                f"rerun of {BASE_DAY} changed row counts "
                f"(staging {staging_base} -> {staging_after}, quarantine {quar_base} -> {quar_after}) — "
                "the load is not idempotent"
            )

    alerts = [a for a in common.read_alerts() if isinstance(a, dict) and "type" in a]
    rate_alerts = [a for a in alerts if a.get("type") == "quarantine_rate"]
    failure_alerts = [a for a in alerts if a.get("type") == "dag_failure"]

    if len(rate_alerts) != 1:
        not_passed(
            f"expected exactly 1 quarantine_rate alert (for {DRILL_DAY}), found {len(rate_alerts)} — "
            "delete data/alerts/alerts.ndjson, rerun the three scenario runs once each, then validate"
        )
    ra = rate_alerts[0]
    if str(ra.get("dt", ""))[:10] != DRILL_DAY:
        not_passed(f"quarantine_rate alert has dt={ra.get('dt')!r}, expected {DRILL_DAY}")
    for key in ("rate", "malformed_count", "invalid_count", "total_lines"):
        if key not in ra:
            not_passed(f"quarantine_rate alert is missing the '{key}' field")
    expected_rate = (ref_drill["malformed"] + ref_drill["invalid_total"]) / ref_drill["total_lines"]
    try:
        got_rate = float(ra["rate"])
    except (TypeError, ValueError):
        not_passed(f"quarantine_rate alert 'rate' is not a number: {ra['rate']!r}")
    if got_rate <= RATE_THRESHOLD:
        not_passed(f"quarantine_rate alert fired with rate {got_rate:.4f}, which is not above the 3% threshold")
    if abs(got_rate - expected_rate) > 0.005:
        not_passed(
            f"quarantine_rate alert rate {got_rate:.4f} does not match the drill day's "
            f"actual quarantine rate {expected_rate:.4f}"
        )

    if not failure_alerts:
        not_passed(f"no dag_failure alert found — trigger the DAG on {MISSING_DAY} (no data dir) and let it fail")
    for fa in failure_alerts:
        if str(fa.get("dt", ""))[:10] != MISSING_DAY:
            not_passed(
                f"dag_failure alert with dt={fa.get('dt')!r} found — only {MISSING_DAY} should ever fail; "
                "fix the DAG, delete data/alerts/alerts.ndjson, and redo the three scenario runs"
            )
        if "dag_id" not in fa or "run_id" not in fa:
            not_passed("dag_failure alert must carry 'dag_id' and 'run_id'")

    passed(
        f"quarantine and staging match ground truth for {BASE_DAY} and {DRILL_DAY}, "
        "rerun is idempotent, alerts are exactly as expected"
    )


if __name__ == "__main__":
    main()
