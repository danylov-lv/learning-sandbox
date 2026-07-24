"""Validator for 20-kubernetes task 18, checkpoint 3 (written mapping +
re-verification).

Run from this task directory:

    uv run python tests/validate_cp3.py

No cluster assertions of its own beyond re-running cp1 and cp2 as real
subprocesses. Three gates:

Gate 1 (doc gate): MAPPING.md's 6 structural sections exist and are
substantial (check_sections), and questions.md's Q1-Q6 are each answered
under "## Hostile-review responses" with original content, not a restated
question or a copy from questions.md (check_answers, questions_path=
anti-copy).

Gate 2: re-runs tests/validate_cp1.py as a subprocess and requires it to
exit 0 with PASSED -- proves the app-of-apps wiring still actually works,
not just that it worked once.

Gate 3: re-runs tests/validate_cp2.py as a subprocess and requires it to
exit 0 with PASSED -- proves the workload is currently sitting in the
post-revert, Synced/Healthy state (this only passes once you've already
done the git revert from cp2's README flow; running cp3 first, before
ever touching cp2, fails here with cp2's own "go revert" message).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_ROOT.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_answers,
    check_sections,
    guarded,
    not_passed,
    passed,
)

MAPPING_PATH = TASK_ROOT / "MAPPING.md"
QUESTIONS_PATH = TASK_ROOT / "questions.md"

REQUIRED_SECTIONS = [
    "Identity and lifecycle",
    "Sources: single vs multi-source",
    "Destination",
    "Sync policy in depth",
    "Ignore differences and drift",
    "Sync waves, hooks, and finalizers",
]

MIN_CHARS = {
    "Identity and lifecycle": 400,
    "Sources: single vs multi-source": 900,
    "Destination": 300,
    "Sync policy in depth": 900,
    "Ignore differences and drift": 700,
    "Sync waves, hooks, and finalizers": 700,
    "_default": 300,
}


def _run_checkpoint(script_name: str) -> str:
    script = TASK_ROOT / "tests" / script_name
    try:
        result = subprocess.run(
            [sys.executable, str(script)], cwd=TASK_ROOT,
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        not_passed(f"{script_name} timed out during cp3's re-verification")

    output = (result.stdout or "").strip()
    last_line = output.splitlines()[-1] if output else (result.stderr.strip() or "(no output)")
    if result.returncode != 0 or "PASSED" not in output:
        not_passed(f"re-run of {script_name} did not pass: {last_line}")
    return last_line


@guarded
def main() -> None:
    check_sections(MAPPING_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = MAPPING_PATH.read_text(encoding="utf-8")
    if "[fill in" in full_text:
        not_passed("MAPPING.md still contains an unfilled '[fill in' marker")

    check_answers(
        MAPPING_PATH,
        [f"Q{i}" for i in range(1, 7)],
        min_answered=6,
        min_chars=250,
        questions_path=QUESTIONS_PATH,
        min_original_chars=200,
    )

    cp1_line = _run_checkpoint("validate_cp1.py")
    cp2_line = _run_checkpoint("validate_cp2.py")

    passed(
        f"MAPPING.md structurally complete, all 6 hostile-review questions answered; "
        f"cp1 re-verified ({cp1_line}); cp2 re-verified ({cp2_line})"
    )


if __name__ == "__main__":
    main()
