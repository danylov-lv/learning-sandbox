"""Validator for 09-prefect-migration.

Run from this task's directory:
    uv run python tests/validate.py

Targets module 06's own warehouse (localhost:54306, db pipelines).
"""

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, load_ground_truth, not_passed, passed, pg_connect  # noqa: E402

FLOW_PATH = TASK_ROOT / "src" / "flow.py"
COMPARISON_PATH = TASK_ROOT / "COMPARISON.md"
VALIDATE_DT = "2025-06-04"
DAG_ID = "prefect:incremental_load"

REQUIRED_HEADINGS = [
    "Scheduling and backfill model",
    "Failure handling and retries",
    "Dev loop and testing",
    "Operational footprint",
    "Where I'd use which",
]

# The unfilled template (as shipped in src/COMPARISON.md, moved to
# COMPARISON.md for the learner to fill) is ~1672 chars of framing
# questions and headings. 1500 chars of real content on top of that
# comfortably rules out "left the template mostly as-is".
MIN_TOTAL_CHARS = 3170


def run_flow():
    return subprocess.run(
        ["uv", "run", "python", str(FLOW_PATH), "--date", VALIDATE_DT],
        cwd=str(TASK_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )


def staging_count(conn, dt):
    with conn.cursor() as cur:
        cur.execute("select count(*) from staging.price_records_raw where dt = %s", (dt,))
        return cur.fetchone()[0]


def audit_row_count(conn, dt):
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from ops.load_audit where dag_id = %s and dt = %s",
            (DAG_ID, dt),
        )
        return cur.fetchone()[0]


@guarded
def main():
    if not FLOW_PATH.exists():
        not_passed(f"missing {FLOW_PATH}")

    gt = load_ground_truth()
    day_gt = gt.get("per_day", {}).get(VALIDATE_DT)
    if day_gt is None:
        not_passed(f"ground truth has no entry for {VALIDATE_DT} — run generate.py from the module root first")
    expected_count = day_gt["parseable_records"]

    conn = pg_connect()

    result1 = run_flow()
    if result1.returncode != 0:
        tail = "\n".join((result1.stdout + result1.stderr).splitlines()[-40:])
        not_passed(f"first run of flow.py exited {result1.returncode}:\n{tail}")

    count1 = staging_count(conn, VALIDATE_DT)
    if count1 != expected_count:
        not_passed(
            f"staging.price_records_raw has {count1} rows for dt={VALIDATE_DT} after first run, "
            f"expected {expected_count} (ground truth parseable_records)"
        )

    result2 = run_flow()
    if result2.returncode != 0:
        tail = "\n".join((result2.stdout + result2.stderr).splitlines()[-40:])
        not_passed(f"second run of flow.py exited {result2.returncode}:\n{tail}")

    count2 = staging_count(conn, VALIDATE_DT)
    if count2 != count1:
        not_passed(
            f"staging.price_records_raw row count for dt={VALIDATE_DT} changed between runs "
            f"({count1} -> {count2}) — the load is not idempotent"
        )

    audits = audit_row_count(conn, VALIDATE_DT)
    if audits < 2:
        not_passed(
            f"ops.load_audit has {audits} row(s) for dag_id='{DAG_ID}', dt={VALIDATE_DT}, expected >= 2 "
            "(one per flow run)"
        )

    conn.close()

    if not COMPARISON_PATH.exists():
        not_passed(f"missing {COMPARISON_PATH}")
    text = COMPARISON_PATH.read_text(encoding="utf-8")

    missing_headings = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing_headings:
        not_passed(f"COMPARISON.md is missing required section heading(s): {missing_headings}")

    if len(text) < MIN_TOTAL_CHARS:
        not_passed(
            f"COMPARISON.md is {len(text)} chars, expected at least {MIN_TOTAL_CHARS} "
            "(looks like the template was left mostly unfilled)"
        )

    passed("flow ran twice idempotently, audit rows present, COMPARISON.md filled in")


if __name__ == "__main__":
    main()
