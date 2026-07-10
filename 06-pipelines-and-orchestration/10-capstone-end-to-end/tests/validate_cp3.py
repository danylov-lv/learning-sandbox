"""CP3 validator for 10-capstone-end-to-end: design writeup + CP1/CP2 re-check.

Checks:
  - DESIGN.md exists at the task root (copied from src/DESIGN_TEMPLATE.md
    and filled in) and contains all six required section headings.
  - DESIGN.md's content, minus the template's own text, is at least 2500
    characters (a length floor, not a quality bar — it exists to keep
    "filled in" honest, not to reward padding).
  - CP1 (validate_cp1.main) and CP2 (both drills, via validate_cp2) still
    pass — a design writeup for a pipeline that no longer works isn't a
    passing capstone.

Run from this task's directory:

    uv run python tests/validate_cp3.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "tests"))

from harness.common import guarded, not_passed, passed  # noqa: E402

DESIGN_PATH = TASK_ROOT / "DESIGN.md"
TEMPLATE_PATH = TASK_ROOT / "src" / "DESIGN_TEMPLATE.md"
MIN_EXTRA_CHARS = 2500

REQUIRED_SECTIONS = [
    "Pipeline topology",
    "Idempotency strategy",
    "Contract strategy and evolution policy",
    "Failure modes and recovery runbook",
    "Alerting policy",
    "What changes at 10x volume",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_design_doc():
    if not TEMPLATE_PATH.exists():
        not_passed(f"template not found at {TEMPLATE_PATH} — module scaffold is broken")
    if not DESIGN_PATH.exists():
        not_passed(f"DESIGN.md not found at {DESIGN_PATH} — copy src/DESIGN_TEMPLATE.md to the task root and fill it in")

    design_text = DESIGN_PATH.read_text(encoding="utf-8")
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")

    missing = [s for s in REQUIRED_SECTIONS if s not in design_text]
    if missing:
        not_passed(f"DESIGN.md is missing required section(s): {missing}")

    extra_chars = len(_normalize(design_text)) - len(_normalize(template_text))
    if extra_chars < MIN_EXTRA_CHARS:
        not_passed(
            f"DESIGN.md has only ~{extra_chars} characters beyond the template "
            f"(need >= {MIN_EXTRA_CHARS}) — fill in real reasoning, not just headings"
        )


@guarded
def main():
    check_design_doc()

    import validate_cp1

    try:
        validate_cp1.main()
    except SystemExit as e:
        if e.code != 0:
            not_passed("CP1 no longer passes — fix the pipeline before finishing the writeup")

    import validate_cp2

    for flag in ("--midstate", "--drift"):
        sys.argv = ["validate_cp2.py", flag]
        try:
            validate_cp2.main()
        except SystemExit as e:
            if e.code != 0:
                not_passed(f"CP2 ({flag}) no longer passes — fix the pipeline before finishing the writeup")

    passed("DESIGN.md complete, CP1 and CP2 both still passing")


if __name__ == "__main__":
    main()
