"""CP3 -- the hostile-review defence, the risk register, the self-critique
memo, and a green re-run of CP1 and CP2.

Checks, in order:

1. `DESIGN.md`'s `## Hostile review responses` and `## Risk register`
   sections exist, clear a minimum length, and contain no placeholder
   markers.
2. Each `### Q1` .. `### Q12` subsection under `## Hostile review
   responses` is genuinely answered -- not missing, not a placeholder,
   not a verbatim copy of the question, and clears a minimum length
   (higher than the other tasks in this module -- this is the capstone).
3. `REVIEW.md`'s `### Weakness 1` / `### Weakness 2` / `### Weakness 3`
   are each genuinely filled in.
4. `validate_cp1.py` and `validate_cp2.py` both still exit 0 when re-run
   as fresh subprocesses (`sys.executable`, not a bare `python` -- that
   matters on Windows -- and not imported in-process, since both call
   `sys.exit` themselves).

Any failure is `NOT PASSED`, naming which check failed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import check_answers, check_sections, guarded, not_passed, passed  # noqa: E402

DESIGN_PATH = TASK_ROOT / "DESIGN.md"
REVIEW_PATH = TASK_ROOT / "REVIEW.md"

REQUIRED_SECTIONS = {
    "Hostile review responses": 3200,
    "Risk register": 500,
}

QUESTION_IDS = [f"Q{i}" for i in range(1, 13)]
_MIN_ANSWERED = 12
_MIN_ANSWER_CHARS = 260  # higher than the other tasks' hostile-review gate

WEAKNESS_IDS = ["Weakness 1", "Weakness 2", "Weakness 3"]
_MIN_WEAKNESSES = 3
_MIN_WEAKNESS_CHARS = 150


def _check_design_doc() -> None:
    check_sections(DESIGN_PATH, list(REQUIRED_SECTIONS.keys()), REQUIRED_SECTIONS)
    check_answers(
        DESIGN_PATH,
        QUESTION_IDS,
        _MIN_ANSWERED,
        min_chars=_MIN_ANSWER_CHARS,
        questions_path=TASK_ROOT / "HOSTILE-REVIEW.md",
    )


def _check_review_doc() -> None:
    if not REVIEW_PATH.exists():
        not_passed("REVIEW.md is missing")
    check_answers(REVIEW_PATH, WEAKNESS_IDS, _MIN_WEAKNESSES, min_chars=_MIN_WEAKNESS_CHARS)


def _run_validator(name: str) -> None:
    script = TASK_ROOT / "tests" / name
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(TASK_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-10:])
        not_passed(f"{name} did not pass on re-run (exit {proc.returncode}):\n{tail}")


@guarded
def main() -> None:
    _check_design_doc()
    _check_review_doc()
    _run_validator("validate_cp1.py")
    _run_validator("validate_cp2.py")
    passed("CP3: hostile review, risk register and self-critique filled in, and CP1 + CP2 both still green")


if __name__ == "__main__":
    main()
