"""Checkpoint 3 checker for 14-capstone-full-audit: hygiene and report.

Run from the module root:
    uv run python 14-capstone-full-audit/tests/check_cp3.py

Gates (see .authoring/tasks-w4-capstone.md for the full verification story):
  1. Vacuum hygiene on orders/payments/inventory_events, using the same
     physical-table checks as 11-vacuum-debt/tests/check.py.
  2. Redundant-index gate on reviews -- same two indexes as
     08-index-audit-reviews/tests/check.py must be gone.
  3. Statistics freshness on orders.status -- a status-filtered probe
     query's worst row-estimate error must be under a calibrated bound.
  4. REPORT.md sections 5-8 present, with a row for every qcNN id in
     section 5's table.
"""

import re
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "tools"))

import psycopg  # noqa: E402

from plan_check import conninfo, get_plan, rows_estimate_error  # noqa: E402
from vacuum_check import check_vacuum_hygiene  # noqa: E402

REPORT_FILE = TASK_ROOT / "REPORT.md"
QC_IDS = [f"qc{n:02d}" for n in range(1, 9)]

DROPPED_REVIEW_INDEXES = ["idx_reviews_product_id", "idx_reviews_review_text"]

# The stock value observed is 649x (see .authoring/tasks-w4-capstone.md);
# a fresh ANALYZE brought it to ~2.9-3.4x in every variant tested. This
# bound sits comfortably between the two, same margin style as
# 07-planner-blindspots/tests/check.py's MAX_ESTIMATE_ERROR.
STATS_PROBE_SQL = """
SELECT count(*) FROM orders
WHERE status = 'processing'
  AND created_at >= now() - interval '14 days'
"""
MAX_ESTIMATE_ERROR = 50.0

REQUIRED_SECTION_HEADINGS = [
    "5. Applied Fixes",
    "6. Hygiene",
    "7. Type-Hygiene Findings",
    "8. Remaining Risks",
]


def check_redundant_indexes(cur, failures):
    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'reviews'")
    present = {row[0] for row in cur.fetchall()}
    still_present = [ix for ix in DROPPED_REVIEW_INDEXES if ix in present]
    if still_present:
        reason = f"reviews: redundant index(es) still present: {', '.join(still_present)}"
        print(f"FAIL  {reason}")
        failures.append(reason)
    else:
        print(f"PASS  reviews: redundant indexes gone ({', '.join(DROPPED_REVIEW_INDEXES)})")


def check_stats_freshness(failures):
    try:
        plan = get_plan(STATS_PROBE_SQL)
    except psycopg.Error as e:
        reason = f"could not run stats-freshness probe query: {e}"
        print(f"FAIL  {reason}")
        failures.append(reason)
        return

    worst, worst_node = rows_estimate_error(plan)

    where = f"{worst_node.get('Node Type')} on {worst_node.get('Relation Name', '?')}" if worst_node else "-"
    if worst > MAX_ESTIMATE_ERROR:
        reason = (
            f"orders.status stats-freshness probe worst estimate error {worst:.1f}x > "
            f"{MAX_ESTIMATE_ERROR}x ({where}) -- pg_stats still looks stale"
        )
        print(f"FAIL  {reason}")
        failures.append(reason)
    else:
        print(f"PASS  orders.status stats-freshness probe worst estimate error {worst:.1f}x <= {MAX_ESTIMATE_ERROR}x")


def find_section(text, heading_prefix):
    pattern = re.compile(
        r"^#{1,3}\s*" + re.escape(heading_prefix.split(".")[0]) + r"\.\s.*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return None
    rest = text[m.end():]
    next_heading = re.search(r"^#{1,3}\s*\d+\.\s", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def check_report(failures):
    if not REPORT_FILE.exists():
        reason = f"{REPORT_FILE.name} not found next to README.md"
        print(f"FAIL  {reason}")
        failures.append(reason)
        return

    text = REPORT_FILE.read_text(encoding="utf-8")
    missing_sections = [h for h in REQUIRED_SECTION_HEADINGS if find_section(text, h) is None]
    if missing_sections:
        reason = f"REPORT.md missing section(s): {', '.join(missing_sections)}"
        print(f"FAIL  {reason}")
        failures.append(reason)
    else:
        print("PASS  REPORT.md has sections 5-8")

    applied = find_section(text, "5. Applied Fixes")
    if applied is not None:
        missing_rows = []
        for qid in QC_IDS:
            row_match = re.search(rf"^\|[^\n]*\b{qid}\b[^\n]*\|", applied, re.MULTILINE)
            if not row_match:
                missing_rows.append(qid)
                continue
            cells = [c.strip() for c in row_match.group(0).strip("|").split("|")]
            if cells[-1] in ("", "-"):
                missing_rows.append(qid)
        if missing_rows:
            reason = f"REPORT.md section 5 table missing/empty row(s) for: {', '.join(missing_rows)}"
            print(f"FAIL  {reason}")
            failures.append(reason)
        else:
            print(f"PASS  REPORT.md section 5 table has all {len(QC_IDS)} qc rows")


def main():
    failures = []

    try:
        with psycopg.connect(conninfo()) as conn, conn.cursor() as cur:
            failures.extend(check_vacuum_hygiene(cur))
            check_redundant_indexes(cur, failures)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not check database hygiene: {e}")
        sys.exit(1)

    check_stats_freshness(failures)
    check_report(failures)

    if failures:
        print(f"NOT PASSED: {'; '.join(failures)}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
