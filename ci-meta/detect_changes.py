"""Map the current diff to the set of changed registry modules.

Runs both inside GitHub Actions (writing `modules` / `any` to
$GITHUB_OUTPUT) and locally (printing the same information to stdout).
Stdlib only.

Base-ref selection:
  - pull_request event: origin/$GITHUB_BASE_REF
  - push event: $GITHUB_EVENT_BEFORE (falls back to HEAD~1 if unset or
    all-zeros, e.g. the first push of a branch)
  - anything else (local run, workflow_dispatch): HEAD~1

A changed path maps to the registry module whose `path` is the longest
matching directory prefix. Files outside every module path (root docs,
.github/, ci-meta/ itself) do not add a module to the matrix -- guards.py
covers repo-wide concerns instead.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

_ZERO_SHA = "0000000000000000000000000000000000000000"


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _pick_base() -> str:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name == "pull_request":
        base_ref = os.environ.get("GITHUB_BASE_REF", "")
        if base_ref:
            return f"origin/{base_ref}"
    elif event_name == "push":
        before = os.environ.get("GITHUB_EVENT_BEFORE", "")
        if before and before != _ZERO_SHA:
            return before
    return "HEAD~1"


def _changed_files(base: str) -> list[str]:
    try:
        out = _run_git(["diff", "--name-only", f"{base}...HEAD"])
    except RuntimeError:
        try:
            out = _run_git(["diff", "--name-only", "HEAD~1"])
        except RuntimeError:
            return []
    return [line for line in out.splitlines() if line]


def map_files_to_modules(files: list[str]) -> list[str]:
    """Longest-prefix-match each file to a registry module id. Order-stable, deduped."""
    module_paths = [(mid, m.path) for mid, m in registry.MODULES.items()]
    matched: set[str] = set()

    for f in files:
        f_posix = f.replace("\\", "/")
        best_id = None
        best_len = -1
        for mid, mpath in module_paths:
            prefix = mpath + "/"
            if f_posix.startswith(prefix) and len(mpath) > best_len:
                best_id = mid
                best_len = len(mpath)
        if best_id is not None:
            matched.add(best_id)

    return [mid for mid in registry.all_module_ids() if mid in matched]


def main() -> int:
    base = _pick_base()
    files = _changed_files(base)
    modules = map_files_to_modules(files)

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"modules={json.dumps(modules)}\n")
            f.write(f"any={'true' if modules else 'false'}\n")

        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## ci-meta: changed modules\n\n")
                f.write(f"Base: `{base}`\n\n")
                if modules:
                    for mid in modules:
                        f.write(f"- `{mid}`\n")
                else:
                    f.write("(none -- no registered module touched by this diff)\n")
    else:
        print(f"base: {base}")
        print(f"changed files: {len(files)}")
        print(json.dumps(modules))
        for mid in modules:
            print(f"  - {mid}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"NOT PASSED: {exc}")
        sys.exit(1)
