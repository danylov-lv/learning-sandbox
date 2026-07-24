"""Shared, stdlib-only check helpers used by run_module_ci.py and repo_guards.py.

Every function here returns (ok: bool, reason: str) and does not raise for
expected failure conditions -- callers wrap the overall flow in their own
try/except per the repo's clean-fail convention.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import registry

REPO_ROOT = Path(__file__).resolve().parent.parent

_PRUNE_DIRS = {
    "node_modules", ".venv", "target", "__pycache__", ".git", "data",
    "dist", "build", ".ruff_cache", ".mypy_cache", ".pytest_cache", "scratch",
    "work",
}

_TASK_DIR_RE = re.compile(r"^\d{2}-")

# Deliverable-doc filenames that, on this repo's stock content, are always
# fill-in templates containing an unfilled marker. INCIDENT.md and
# HOSTILE-REVIEW.md are deliberately excluded: in this repo they are
# sometimes "given" read-only input docs (a raw incident record, a fixed
# list of hostile-review questions answered elsewhere) rather than
# templates the learner fills in directly, so requiring a marker in them
# produces false positives on legitimate stock content.
_DELIVERABLE_DOC_NAMES = (
    "ANSWER.md", "DESIGN.md", "POLICY.md", "REVIEW.md",
    "MAPPING.md", "RECON.md", "ANALYSIS.md",
)

_UNFILLED_MARKERS = ("fill in", "[fill", "answer here")


def _iter_source_files(module_dir: Path, extensions: tuple[str, ...]):
    for dirpath, dirnames, filenames in os.walk(module_dir):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for name in filenames:
            if name.endswith(extensions):
                yield Path(dirpath) / name


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _iter_named_files(module_dir: Path, names: tuple[str, ...]):
    """Exact, case-sensitive filename match, independent of the host
    filesystem's own case (in)sensitivity -- Path.rglob(name) is
    case-insensitive on Windows, which would wrongly match e.g. an
    .authoring/design.md notes file against a DESIGN.md deliverable name.
    """
    for dirpath, dirnames, filenames in os.walk(module_dir):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for name in filenames:
            if name in names:
                yield Path(dirpath) / name


def _task_dirs(module_dir: Path) -> list[Path]:
    return sorted(
        p for p in module_dir.iterdir()
        if p.is_dir() and (_TASK_DIR_RE.match(p.name) or p.name == "k8s-bonus")
    )


def check_required_files(module_id: str) -> tuple[bool, str]:
    try:
        entry = registry.get(module_id)
    except KeyError as exc:
        return False, str(exc)

    module_dir = REPO_ROOT / entry.path
    if not module_dir.is_dir():
        return False, f"module directory not found: {entry.path}"

    task_dirs = _task_dirs(module_dir)
    if not task_dirs:
        return False, f"no task directories found under {entry.path}"

    for task_dir in task_dirs:
        rel = f"{entry.path}/{task_dir.name}"
        if not (task_dir / "README.md").is_file():
            return False, f"{rel} is missing README.md"
        if not (task_dir / "NOTES.md").is_file():
            return False, f"{rel} is missing NOTES.md"
        hints_dir = task_dir / "hints"
        if hints_dir.is_dir():
            for hint in ("hint-1.md", "hint-2.md", "hint-3.md"):
                if not (hints_dir / hint).is_file():
                    return False, f"{rel}/hints is missing {hint}"

    if entry.kind == "python":
        if not (module_dir / "pyproject.toml").is_file():
            return False, f"{entry.path} is missing pyproject.toml"
        if not (module_dir / "uv.lock").is_file():
            return False, f"{entry.path} is missing uv.lock"
    elif entry.kind == "rust":
        has_manifest = (module_dir / "Cargo.toml").is_file() or any(module_dir.rglob("Cargo.toml"))
        has_lock = (module_dir / "Cargo.lock").is_file() or any(module_dir.rglob("Cargo.lock"))
        if not (has_manifest and has_lock):
            return False, f"{entry.path} is missing a Cargo.toml/Cargo.lock pair"
    elif entry.kind == "pnpm":
        if not (module_dir / "package.json").is_file():
            return False, f"{entry.path} is missing package.json"
        if not (module_dir / "pnpm-lock.yaml").is_file():
            return False, f"{entry.path} is missing pnpm-lock.yaml"
    else:
        return False, f"{entry.path} has unknown kind {entry.kind!r}"

    return True, "ok"


def _git_ls_files(pathspec: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", pathspec],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def check_no_solution(module_id: str) -> tuple[bool, str]:
    try:
        entry = registry.get(module_id)
    except KeyError as exc:
        return False, str(exc)

    module_dir = REPO_ROOT / entry.path

    try:
        tracked = _git_ls_files(entry.path)
    except (subprocess.CalledProcessError, OSError) as exc:
        return False, f"git ls-files failed for {entry.path}: {exc}"

    for f in tracked:
        if Path(f).name.startswith("solution."):
            return False, f"tracked solution file leaked: {f}"

    # Search only inside task directories (the learner-facing tree), not the
    # module root's harness/seed/validate.py -- those are infra scripts that
    # legitimately never need to contain a stub marker. Some modules ship
    # raw .sql/.sh task deliverables with no .py/.rs/.ts files under any task
    # dir at all, or (16-testing-engineering, the toolkit modules) use a
    # per-task placeholder convention other than the kind's generic marker
    # (a "given, not edited" real config to fix, an instructional comment
    # block, a real git repo state) -- these are "legitimately has no such
    # tree" cases. rust and pnpm are single, homogeneous task shapes with a
    # confirmed-consistent marker across every task, so absence there is
    # hard-failed; python spans 20+ wildly different task shapes across this
    # repo, so absence there is best-effort/informational only, never fails.
    ext_map = {"python": (".py",), "rust": (".rs",), "pnpm": (".ts", ".tsx")}
    markers = registry.stub_marker(entry.kind)
    source_files = [
        f for task_dir in _task_dirs(module_dir)
        for f in _iter_source_files(task_dir, ext_map[entry.kind])
    ]
    if source_files and entry.kind in ("rust", "pnpm"):
        found = any(
            any(marker in _read_text(path) for marker in markers)
            for path in source_files
        )
        if not found:
            return False, (
                f"no stub marker ({'/'.join(markers)}) found anywhere under "
                f"{entry.path}'s source tree -- possible solution leak"
            )

    for doc_path in _iter_named_files(module_dir, _DELIVERABLE_DOC_NAMES):
        text = _read_text(doc_path).lower()
        if text and not any(marker in text for marker in _UNFILLED_MARKERS):
            rel = doc_path.relative_to(REPO_ROOT)
            return False, f"deliverable doc template appears filled in: {rel}"

    return True, "ok"
