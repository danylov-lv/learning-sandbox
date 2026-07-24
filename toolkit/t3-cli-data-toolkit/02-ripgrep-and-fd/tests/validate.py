"""Validator for 02-ripgrep-and-fd. Run from the module root:

    cd toolkit/t3-cli-data-toolkit
    uv run python 02-ripgrep-and-fd/tests/validate.py

Runs src/solve.sh, parses its four ===Qn=== stdout blocks, and compares
each against an independent recomputation over data/filetree/ done here in
plain Python (re + pathlib) -- never by re-running rg/fd with different
flags and trusting agreement.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    not_passed,
    parse_marker_sections,
    passed,
    require_data,
    run_script,
)

LABELS = ["Q1", "Q2", "Q3", "Q4"]
EXTENSIONS = ["py", "js", "log", "md", "json"]

STATUS_RE = re.compile(r"status=(5\d\d)")
LOOKAROUND_RE = re.compile(r"price(?!_usd)")


def _expected_q1(filetree: Path) -> str:
    codes = set()
    for log_path in filetree.rglob("*.log"):
        if "logs" not in log_path.relative_to(filetree).parts:
            continue
        text = log_path.read_text(encoding="utf-8", errors="replace")
        codes.update(STATUS_RE.findall(text))
    return ",".join(sorted(codes))


def _expected_q2(filetree: Path) -> list:
    paths = []
    for p in filetree.rglob("*.config.json"):
        rel = p.relative_to(filetree)
        if "vendor" in rel.parts:
            continue
        paths.append(rel.as_posix())
    return sorted(paths)


def _expected_q3(filetree: Path) -> int:
    src_dir = filetree / "src"
    total = 0
    for ext in ("*.py", "*.js"):
        for p in src_dir.rglob(ext):
            text = p.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                total += len(LOOKAROUND_RE.findall(line))
    return total


def _expected_q4(filetree: Path) -> dict:
    counts = {ext: 0 for ext in EXTENSIONS}
    for p in filetree.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lstrip(".")
        if ext in counts:
            counts[ext] += 1
    return counts


@guarded
def main() -> None:
    filetree = require_data("filetree")

    expected_q1 = _expected_q1(filetree)
    expected_q2 = _expected_q2(filetree)
    expected_q3 = _expected_q3(filetree)
    expected_q4 = _expected_q4(filetree)

    result = run_script(TASK_DIR / "src" / "solve.sh")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        not_passed(f"src/solve.sh exited {result.returncode}: {tail}")

    sections = parse_marker_sections(result.stdout, LABELS)

    actual_q1 = sections["Q1"].strip()
    if actual_q1 != expected_q1:
        not_passed(f"Q1: got '{actual_q1}', expected '{expected_q1}'")

    actual_q2 = sorted(line.strip() for line in sections["Q2"].splitlines() if line.strip())
    if actual_q2 != expected_q2:
        not_passed(
            f"Q2: got {len(actual_q2)} path(s), expected {len(expected_q2)}.\n"
            f"  got:      {actual_q2}\n  expected: {expected_q2}"
        )

    try:
        actual_q3 = int(sections["Q3"].strip())
    except ValueError:
        not_passed(f"Q3: '{sections['Q3'].strip()}' is not an integer")
    if actual_q3 != expected_q3:
        not_passed(f"Q3: got {actual_q3}, expected {expected_q3}")

    actual_q4 = {}
    for line in sections["Q4"].splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            not_passed(f"Q4: line '{line}' is not in 'ext:count' form")
        ext, _, count_str = line.partition(":")
        try:
            actual_q4[ext.strip()] = int(count_str.strip())
        except ValueError:
            not_passed(f"Q4: line '{line}' has a non-integer count")
    if actual_q4 != expected_q4:
        not_passed(f"Q4: got {actual_q4}, expected {expected_q4}")

    passed("all four answers verified")


if __name__ == "__main__":
    main()
