"""Repo-wide invariants, independent of which module changed.

Runs on every push/PR (see .github/workflows/ci.yml's `guards` job).
Stdlib only.

Checks:
  1. no tracked junk matching the .gitignore junk patterns
  2. GENERATION_STATE.md has no remaining `- [ ]` pending lines
  3. registry.py covers exactly the real module directories on disk
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# (compiled pattern, human description). Mirrors .gitignore's junk entries,
# except data/ground-truth.json which is the one intentionally committed
# data file.
_JUNK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(^|/)\.venv/"), ".venv/"),
    (re.compile(r"(^|/)__pycache__(/|$)"), "__pycache__"),
    (re.compile(r"\.pyc$"), "*.pyc"),
    (re.compile(r"-local\.json$"), "*-local.json"),
    (re.compile(r"(^|/)scratch/"), "scratch/"),
    (re.compile(r"(^|/)work/"), "work/"),
    (re.compile(r"(^|/)node_modules/"), "node_modules/"),
    (re.compile(r"(^|/)target/"), "target/"),
    (re.compile(r"(^|/)\.ruff_cache/"), ".ruff_cache/"),
    (re.compile(r"(^|/)\.mypy_cache/"), ".mypy_cache/"),
    (re.compile(r"(^|/)solution\.[^/]+$"), "solution.*"),
]

_DATA_DIR_RE = re.compile(r"(^|/)data/")
_ALLOWED_DATA_FILE = "data/ground-truth.json"

# 13-scraping-at-scale/docker/target/ is the mock target site's Docker
# build context (a directory legitimately named "target"), not a Rust
# build-artifact directory -- excluded from the target/ junk pattern.
_ALLOWED_TARGET_PREFIX = "13-scraping-at-scale/docker/target/"

_TASK_DIR_RE = re.compile(r"^\d{2}-")
_TOOLKIT_DIR_RE = re.compile(r"^t\d+-")


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def check_no_tracked_junk() -> tuple[bool, str]:
    tracked = _git_ls_files()
    offenders = []
    for f in tracked:
        if _DATA_DIR_RE.search(f) and not f.endswith(_ALLOWED_DATA_FILE):
            offenders.append(f)
            continue
        if f.startswith(_ALLOWED_TARGET_PREFIX):
            continue
        for pattern, _desc in _JUNK_PATTERNS:
            if pattern.search(f):
                offenders.append(f)
                break
    if offenders:
        sample = ", ".join(offenders[:5])
        more = f" (+{len(offenders) - 5} more)" if len(offenders) > 5 else ""
        return False, f"tracked junk files found: {sample}{more}"
    return True, "ok"


def check_generation_state_complete() -> tuple[bool, str]:
    path = REPO_ROOT / "GENERATION_STATE.md"
    if not path.is_file():
        return False, "GENERATION_STATE.md not found"
    pending = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if re.match(r"^\s*-\s*\[\s*\]", line):
            pending.append((lineno, line.strip()))
    if pending:
        lineno, text = pending[0]
        more = f" (+{len(pending) - 1} more)" if len(pending) > 1 else ""
        return False, f"GENERATION_STATE.md has pending items, e.g. line {lineno}: {text}{more}"
    return True, "ok"


def _real_module_dirs() -> set[str]:
    real: set[str] = set()
    for entry in REPO_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "toolkit":
            for sub in entry.iterdir():
                if sub.is_dir() and _TOOLKIT_DIR_RE.match(sub.name):
                    real.add(f"toolkit/{sub.name}")
        elif _TASK_DIR_RE.match(entry.name):
            real.add(entry.name)
    return real


def check_registry_matches_disk() -> tuple[bool, str]:
    real = _real_module_dirs()
    registered = set(registry.all_module_ids())

    missing_from_registry = sorted(real - registered)
    missing_from_disk = sorted(registered - real)

    if missing_from_registry or missing_from_disk:
        parts = []
        if missing_from_registry:
            parts.append(f"on disk but not registered: {missing_from_registry}")
        if missing_from_disk:
            parts.append(f"registered but no directory on disk: {missing_from_disk}")
        return False, "; ".join(parts)
    return True, "ok"


CHECKS = (
    ("no tracked junk", check_no_tracked_junk),
    ("GENERATION_STATE.md complete", check_generation_state_complete),
    ("registry matches disk", check_registry_matches_disk),
)


def main() -> int:
    failures = []
    for name, fn in CHECKS:
        ok, reason = fn()
        if not ok:
            failures.append(f"{name}: {reason}")

    if failures:
        for f in failures:
            print(f"::error::{f}")
        print(f"NOT PASSED: {'; '.join(failures)}")
        return 1

    print("PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"NOT PASSED: {exc}")
        sys.exit(1)
