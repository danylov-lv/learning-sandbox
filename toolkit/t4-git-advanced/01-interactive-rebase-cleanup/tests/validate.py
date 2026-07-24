"""Validator for 01-interactive-rebase-cleanup. Run from the task directory:

    uv run python tests/validate.py

Repo-state validator: never inspects *how* the learner rebased, only the
resulting state of work/'s `main` branch -- commit count, linearity, exact
messages in order, absence of the dropped debug commit/file, and byte-exact
final content of the two tracked files.
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

EXPECTED_MESSAGES = [
    "Initial commit",
    "add threshold check",
    "Add price alert logic",
    "add email notification channel",
    "update README",
]

EXPECTED_PRICE_ALERT_PY = '''"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def send_alert(product, change_pct, channel="console"):
    message = f"ALERT: {product} moved {change_pct:.1f}%"
    if channel.lower() == "email":
        return f"[email] {message}"
    return message


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return abs(change_pct) >= threshold_pct
'''

EXPECTED_README_MD = """# price-alert

Scratch project for the git rebase cleanup exercise.

## Usage

    from price_alert import check_threshold, send_alert

    if check_threshold(old, new, 5.0):
        send_alert("widget", (new - old) / old * 100, channel="email")
"""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(WORK_DIR), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        not_passed(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


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

    branches = _git("branch", "--list", "main").strip()
    if not branches:
        not_passed("branch 'main' not found in work/ -- did you rename or delete it?")

    log = _git("log", "--format=%H %P", "main").strip()
    if not log:
        not_passed("main has no commits")
    lines = log.splitlines()

    commits = []
    for line in lines:
        parts = line.split(" ")
        sha = parts[0]
        parents = parts[1:]
        commits.append((sha, parents))
    # log is newest-first; walk oldest-first for message comparison
    commits_oldest_first = list(reversed(commits))

    got_count = len(commits_oldest_first)
    if got_count != len(EXPECTED_MESSAGES):
        not_passed(
            f"main has {got_count} commit(s), expected {len(EXPECTED_MESSAGES)}"
        )

    for i, (sha, parents) in enumerate(commits_oldest_first):
        if i == 0:
            if len(parents) != 0:
                not_passed(f"commit {i + 1} (root) has {len(parents)} parent(s), expected 0")
        else:
            if len(parents) != 1:
                not_passed(
                    f"commit {i + 1} has {len(parents)} parent(s), expected 1 -- "
                    "history must be linear (no merge commits)"
                )

    messages = _git("log", "--format=%s", "--reverse", "main").splitlines()
    if messages != EXPECTED_MESSAGES:
        not_passed(
            f"commit messages (oldest to newest) are {messages!r}, "
            f"expected {EXPECTED_MESSAGES!r}"
        )

    for msg in messages:
        if msg.startswith("fixup!") or msg.startswith("squash!") or msg.startswith("WIP"):
            not_passed(f"leftover unsquashed/undropped commit message: {msg!r}")

    tree_files = set(_git("ls-tree", "-r", "--name-only", "main").splitlines())
    if "debug.log" in tree_files:
        not_passed("debug.log is still present in the final tree -- the debug commit must be dropped")

    expected_files = {".gitattributes", "price_alert.py", "README.md"}
    if tree_files != expected_files:
        not_passed(f"final tree has {sorted(tree_files)}, expected {sorted(expected_files)}")

    actual_price_alert = _blob_at("main", "price_alert.py")
    if actual_price_alert is None:
        not_passed("price_alert.py missing from final tree")
    if actual_price_alert != EXPECTED_PRICE_ALERT_PY:
        not_passed(
            "price_alert.py content differs from the intended final content -- "
            "cleanup must not change what the code does, only the history"
        )

    actual_readme = _blob_at("main", "README.md")
    if actual_readme is None:
        not_passed("README.md missing from final tree")
    if actual_readme != EXPECTED_README_MD:
        not_passed(
            "README.md content differs from the intended final content -- "
            "cleanup must not change what the code does, only the history"
        )

    passed(f"main: {got_count} linear commits, messages and tree match target")


if __name__ == "__main__":
    main()
