"""Validator for 05-gnu-parallel-batch. Run from the module root:

    cd toolkit/t3-cli-data-toolkit
    uv run python 05-gnu-parallel-batch/tests/validate.py

Wipes data/batch/outputs/ + the joblog, runs src/solve.sh, then checks the
joblog for evidence of parallel execution and diffs every output file
against a serial reference this validator computes independently in
Python from the same inputs -- never against the learner's own output as
its own oracle.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import check_close, guarded, not_passed, passed, require_data, run_script  # noqa: E402

OUTPUTS_DIR = MODULE_ROOT / "data" / "batch" / "outputs"
JOBLOG_PATH = MODULE_ROOT / "data" / "batch" / "joblog.txt"

JOBS_FLAG_RE = re.compile(r"(?:--jobs(?:[= ]|\s+)|-j\s*)(\d+)")


def _check_script_flags(script_path: Path) -> None:
    text = script_path.read_text(encoding="utf-8")
    if "parallel" not in text:
        not_passed("src/solve.sh doesn't appear to invoke `parallel`")
    m = JOBS_FLAG_RE.search(text)
    if not m or int(m.group(1)) < 2:
        not_passed("src/solve.sh must pass --jobs N (or -j N) with N >= 2")
    if "--joblog" not in text:
        not_passed("src/solve.sh must pass --joblog data/batch/joblog.txt")


def _expected_summary(input_path: Path) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    listings = data["listings"]
    total = sum(l["price_cents"] for l in listings) / 100
    count = len(listings)
    categories = sorted({l["category"] for l in listings})
    return {
        "page_id": data["page_id"],
        "listing_count": count,
        "total_price_usd": total,
        "avg_price_usd": total / count,
        "categories": categories,
    }


@guarded
def main() -> None:
    inputs_dir = require_data("batch", "inputs")
    input_paths = sorted(inputs_dir.glob("*.json"))
    if not input_paths:
        not_passed(f"no input files found under {inputs_dir}")

    script_path = TASK_DIR / "src" / "solve.sh"
    _check_script_flags(script_path)

    if OUTPUTS_DIR.exists():
        shutil.rmtree(OUTPUTS_DIR)
    if JOBLOG_PATH.exists():
        JOBLOG_PATH.unlink()

    result = run_script(script_path, cwd=MODULE_ROOT, timeout=120.0)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        not_passed(f"src/solve.sh exited {result.returncode}: {tail}")

    if not JOBLOG_PATH.exists():
        not_passed(f"{JOBLOG_PATH.relative_to(MODULE_ROOT)} was not created")
    joblog_lines = [ln for ln in JOBLOG_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(joblog_lines) < 2:
        not_passed("joblog has no job rows (only a header, or empty)")
    header = joblog_lines[0].split("\t")
    try:
        exitval_col = header.index("Exitval")
    except ValueError:
        not_passed("joblog header doesn't look like a GNU parallel joblog (no 'Exitval' column)")
    job_rows = joblog_lines[1:]
    if len(job_rows) != len(input_paths):
        not_passed(f"joblog has {len(job_rows)} job row(s), expected {len(input_paths)} (one per input file)")
    for row in job_rows:
        cols = row.split("\t")
        if len(cols) <= exitval_col or cols[exitval_col] != "0":
            not_passed(f"joblog records a non-zero exit code in row: {row!r}")

    for input_path in input_paths:
        out_path = OUTPUTS_DIR / input_path.name
        if not out_path.exists():
            not_passed(f"missing output file: {out_path.relative_to(MODULE_ROOT)}")
        try:
            actual = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            not_passed(f"{out_path.name}: not valid JSON: {e}")

        expected = _expected_summary(input_path)

        for field in ("page_id", "listing_count", "categories"):
            if actual.get(field) != expected[field]:
                not_passed(f"{out_path.name}: '{field}' got {actual.get(field)!r}, expected {expected[field]!r}")

        for field in ("total_price_usd", "avg_price_usd"):
            if field not in actual:
                not_passed(f"{out_path.name}: missing '{field}'")
            check_close(actual[field], expected[field], rel_tol=1e-6, label=f"{out_path.name} {field}")

    passed(f"{len(input_paths)} output files verified against {len(job_rows)} joblog rows")


if __name__ == "__main__":
    main()
