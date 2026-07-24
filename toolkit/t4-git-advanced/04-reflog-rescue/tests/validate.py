"""Validator for 04-reflog-rescue. Run from the task directory:

    uv run python tests/validate.py

Repo-state validator against SHAs known independently: setup.sh is
deterministic (fixed author/committer dates, fixed content), so the lost
commit's exact SHA was captured once by running setup.sh and is hardcoded
below -- see .authoring/design.md. A recreated-but-not-identical commit
(same message, same file content, different SHA) does not pass; recovery
must point at the literal original object.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
WORK_DIR = TASK_DIR / "work"
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

EXPECTED_MAIN_SHA = "b2d59f58502657dd74b78d3ef3fa6d042412add6"
EXPECTED_LOST_TIP_SHA = "3ce744f4e10a99e00b035bc10d68739ede711090"
LOST_BRANCH = "feature/valuable-work"


def _rev_parse(ref: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


@guarded
def main() -> None:
    if not (WORK_DIR / ".git").exists():
        not_passed(f"no git repo at {WORK_DIR} -- run setup.sh first")

    main_sha = _rev_parse("main")
    if main_sha is None:
        not_passed("branch 'main' not found in work/")
    if main_sha != EXPECTED_MAIN_SHA:
        not_passed(
            f"main's tip is {main_sha}, expected {EXPECTED_MAIN_SHA} -- "
            "main must stay exactly as setup.sh left it"
        )

    recovered_sha = _rev_parse(LOST_BRANCH)
    if recovered_sha is None:
        not_passed(f"branch '{LOST_BRANCH}' does not exist -- it was deleted by setup.sh, recover it")

    if recovered_sha != EXPECTED_LOST_TIP_SHA:
        not_passed(
            f"'{LOST_BRANCH}' points at {recovered_sha}, expected the original lost "
            f"commit {EXPECTED_LOST_TIP_SHA} -- recovery must point the branch at the "
            "literal original commit object (e.g. found via 'git reflog'), not a new "
            "commit that merely matches its content"
        )

    passed(f"'{LOST_BRANCH}' recovered at the original commit {EXPECTED_LOST_TIP_SHA}; main untouched")


if __name__ == "__main__":
    main()
