"""Validator for 02-bisect-find-regression. Run from the task directory:

    uv run python tests/validate.py

Never trusts any `git bisect` state the learner may have left behind.
Instead it independently walks work/'s full commit history itself,
running is_bad.sh at every commit in order, and determines the true
first-bad commit from scratch -- then compares that against
FIRST_BAD_SHA.txt.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
WORK_DIR = TASK_DIR / "work"
ANSWER_FILE = TASK_DIR / "FIRST_BAD_SHA.txt"
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        not_passed(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _is_bad(sha: str) -> bool:
    checkout = subprocess.run(
        ["git", "-C", str(WORK_DIR), "checkout", "-q", "--detach", sha],
        capture_output=True,
        text=True,
    )
    if checkout.returncode != 0:
        not_passed(f"could not check out {sha}: {checkout.stderr.strip()}")
    result = subprocess.run(
        ["bash", "is_bad.sh"],
        cwd=str(WORK_DIR),
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


@guarded
def main() -> None:
    if not (WORK_DIR / ".git").exists():
        not_passed(f"no git repo at {WORK_DIR} -- run setup.sh first")
    if not (WORK_DIR / "is_bad.sh").exists():
        not_passed("is_bad.sh not found in work/ -- run setup.sh first")

    if not ANSWER_FILE.exists():
        not_passed(f"answer file not found: {ANSWER_FILE}")
    answer = ANSWER_FILE.read_text(encoding="utf-8").strip()
    if not answer or answer == "PASTE_FULL_SHA_HERE":
        not_passed("FIRST_BAD_SHA.txt still has the placeholder -- fill in the SHA you found")
    if len(answer) != 40 or any(c not in "0123456789abcdef" for c in answer.lower()):
        not_passed(f"FIRST_BAD_SHA.txt does not look like a full 40-char SHA: {answer!r}")

    shas = _git("log", "--format=%H", "--reverse", "main").split()
    if not shas:
        not_passed("main has no commits")

    original_head = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if original_head == "HEAD":
        original_head = _git("rev-parse", "HEAD").strip()

    first_bad = None
    try:
        for sha in shas:
            if _is_bad(sha):
                first_bad = sha
                break
    finally:
        subprocess.run(
            ["git", "-C", str(WORK_DIR), "checkout", "-q", original_head],
            capture_output=True,
            text=True,
        )

    if first_bad is None:
        not_passed("independent walk found no bad commit at all in main's history -- fixture problem, not a learner error")

    answer_norm = answer.lower()
    if answer_norm != first_bad:
        not_passed(
            f"FIRST_BAD_SHA.txt has {answer_norm}, but the first commit where "
            f"is_bad.sh fails is {first_bad}"
        )

    passed(f"first bad commit correctly identified: {first_bad}")


if __name__ == "__main__":
    main()
