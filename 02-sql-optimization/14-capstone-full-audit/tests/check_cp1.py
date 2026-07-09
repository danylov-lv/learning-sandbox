"""Checkpoint 1 checker for 14-capstone-full-audit: diagnose and baseline.

Run from the module root:
    uv run python 14-capstone-full-audit/tests/check_cp1.py

Gates on completeness only, not prose quality (prose can't be machine-graded):
  1. baseline-local.json at the module root has a recorded entry for every
     qc01..qc08 query id.
  2. REPORT.md exists next to this task's README.md, with sections 1-4
     present, and section 2's triage table has a row for every qc id with a
     non-empty root-cause cell.
"""

import re
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = MODULE_ROOT / "baseline-local.json"
REPORT_FILE = TASK_ROOT / "REPORT.md"

QC_IDS = [f"qc{n:02d}" for n in range(1, 9)]

REQUIRED_SECTION_HEADINGS = [
    "1. Inventory",
    "2. Workload Triage",
    "3. Root-Cause Map",
    "4. Fix Plan",
]


def load_baseline():
    import json

    if not BASELINE_FILE.exists():
        return {}
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def find_section(text, heading_prefix):
    """Return the text of a '## <n>. <name>' section (heading matched
    loosely by its leading number + first couple words), up to the next
    '## ' heading."""
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


def main():
    failures = []

    baseline = load_baseline()
    missing_baselines = [qid for qid in QC_IDS if qid not in baseline]
    if missing_baselines:
        reason = (
            f"baseline-local.json missing entries for: {', '.join(missing_baselines)} "
            "-- run tools/baseline.py record for every workload/qcNN.sql first"
        )
        print(f"FAIL  {reason}")
        failures.append(reason)
    else:
        print(f"PASS  baseline-local.json has all {len(QC_IDS)} qc entries")

    if not REPORT_FILE.exists():
        reason = f"{REPORT_FILE.name} not found next to README.md -- copy REPORT_TEMPLATE.md to REPORT.md and fill it in"
        print(f"FAIL  {reason}")
        failures.append(reason)
    else:
        text = REPORT_FILE.read_text(encoding="utf-8")

        missing_sections = []
        for heading in REQUIRED_SECTION_HEADINGS:
            if find_section(text, heading) is None:
                missing_sections.append(heading)
        if missing_sections:
            reason = f"REPORT.md missing section(s): {', '.join(missing_sections)}"
            print(f"FAIL  {reason}")
            failures.append(reason)
        else:
            print("PASS  REPORT.md has sections 1-4")

        triage = find_section(text, "2. Workload Triage")
        if triage is not None:
            missing_rows = []
            for qid in QC_IDS:
                row_match = re.search(
                    rf"^\|[^\n]*\b{qid}\b[^\n]*\|", triage, re.MULTILINE
                )
                if not row_match:
                    missing_rows.append(qid)
                    continue
                row = row_match.group(0)
                cells = [c.strip() for c in row.strip("|").split("|")]
                root_cause_cell = cells[-1] if cells else ""
                if root_cause_cell in ("", "-"):
                    missing_rows.append(qid)
            if missing_rows:
                reason = f"REPORT.md section 2 triage table missing/empty row(s) for: {', '.join(missing_rows)}"
                print(f"FAIL  {reason}")
                failures.append(reason)
            else:
                print(f"PASS  REPORT.md section 2 triage table has all {len(QC_IDS)} qc rows")

    if failures:
        print(f"NOT PASSED: {'; '.join(failures)}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
