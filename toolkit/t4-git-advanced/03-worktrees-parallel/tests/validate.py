"""Validator for 03-worktrees-parallel. Run from the task directory:

    uv run python tests/validate.py

Repo-state validator: checks the two feature branches' end-states
(commit count ahead of main, message, exact file content) and confirms
`git worktree list` currently reports both worktrees still attached --
evidence the worktree mechanism was actually used, not just two branches
created by hand.
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

EXPECTED_MAIN_SHA = "e9ac3765fd2318feb5c785ea5bc715606af1eda8"

BRANCHES = {
    "feature/alpha": {
        "message": "Add alpha note",
        "file": "alpha-note.txt",
        "content": "alpha worked on: parallel scraping fixes\n",
        "worktree": ".worktrees/alpha",
    },
    "feature/beta": {
        "message": "Add beta note",
        "file": "beta-note.txt",
        "content": "beta worked on: retry backoff tuning\n",
        "worktree": ".worktrees/beta",
    },
}


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        not_passed(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _rev_parse(ref: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _blob_at(rev: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), "show", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


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

    for branch, spec in BRANCHES.items():
        branch_sha = _rev_parse(branch)
        if branch_sha is None:
            not_passed(f"branch '{branch}' not found in work/")

        ahead = _git("rev-list", "--count", f"main..{branch}").strip()
        if ahead != "1":
            not_passed(f"'{branch}' is {ahead} commit(s) ahead of main, expected exactly 1")

        behind = _git("rev-list", "--count", f"{branch}..main").strip()
        if behind != "0":
            not_passed(f"'{branch}' is missing {behind} commit(s) that main has -- it must be based on main")

        tip_message = _git("log", "-1", "--format=%s", branch).strip()
        if tip_message != spec["message"]:
            not_passed(f"'{branch}' tip commit message is {tip_message!r}, expected {spec['message']!r}")

        branch_files = set(_git("ls-tree", "-r", "--name-only", branch).splitlines())
        main_files = set(_git("ls-tree", "-r", "--name-only", "main").splitlines())
        new_files = branch_files - main_files
        if new_files != {spec["file"]}:
            not_passed(
                f"'{branch}' adds file(s) {sorted(new_files)} relative to main, "
                f"expected exactly {{{spec['file']!r}}}"
            )

        content = _blob_at(branch, spec["file"])
        if content != spec["content"]:
            not_passed(
                f"'{branch}':{spec['file']} content is {content!r}, expected {spec['content']!r}"
            )

    worktree_list = _git("worktree", "list", "--porcelain")
    entries: list[dict] = []
    current: dict = {}
    for line in worktree_list.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        parts = line.split(" ", 1)
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        current[key] = value
    if current:
        entries.append(current)

    for branch, spec in BRANCHES.items():
        expected_path = (WORK_DIR / spec["worktree"]).resolve()
        expected_branch_ref = f"refs/heads/{branch}"
        match = None
        for entry in entries:
            entry_path = entry.get("worktree", "")
            if not entry_path:
                continue
            if Path(entry_path).resolve() == expected_path:
                match = entry
                break
        if match is None:
            not_passed(
                f"git worktree list has no entry at {expected_path} -- "
                f"worktree for '{branch}' must still exist (don't remove it before validating)"
            )
        if match.get("branch") != expected_branch_ref:
            not_passed(
                f"worktree at {expected_path} is bound to {match.get('branch')!r}, "
                f"expected {expected_branch_ref!r}"
            )

    passed("both feature branches correct, main untouched, both worktrees still attached")


if __name__ == "__main__":
    main()
