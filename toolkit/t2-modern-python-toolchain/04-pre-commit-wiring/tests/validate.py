"""Validator for 04-pre-commit-wiring. Run from the module root:

    cd toolkit/t2-modern-python-toolchain
    uv run python 04-pre-commit-wiring/tests/validate.py

Checks, in order:
  1. `.pre-commit-config.yaml` exists in this task directory (it's the
     deliverable — there is no scaffold to start from) and structurally
     wires the five required hooks: ruff (lint), ruff-format, mypy (with
     --strict), trailing-whitespace, end-of-file-fixer.
  2. In a throwaway git repo under scratch/: the CLEAN fixture plus the
     learner's config passes `pre-commit run --all-files` cleanly.
  3. The same repo, with the BAD fixture swapped in, FAILS
     `pre-commit run --all-files` — proving the hooks actually catch a
     real problem, not just that the config parses.
  4. scratch/ is removed afterward either way.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    cleanup_scratch,
    fresh_scratch_dir,
    guarded,
    load_yaml,
    not_passed,
    passed,
    run,
)

CONFIG_PATH = TASK_DIR / ".pre-commit-config.yaml"
FIXTURES_CLEAN = TASK_DIR / "fixtures" / "clean"
FIXTURES_BAD = TASK_DIR / "fixtures" / "bad"

REQUIRED_HOOK_IDS = {
    "ruff",
    "ruff-format",
    "mypy",
    "trailing-whitespace",
    "end-of-file-fixer",
}


def _all_hooks(config: dict) -> list[dict]:
    hooks = []
    for repo in config.get("repos", []):
        for hook in repo.get("hooks", []):
            hooks.append(hook)
    return hooks


def _check_structure() -> None:
    if not CONFIG_PATH.exists():
        not_passed(
            f"{CONFIG_PATH.relative_to(TASK_DIR)} not found — write it, it's this "
            "task's deliverable"
        )
    config = load_yaml(CONFIG_PATH)
    if not isinstance(config.get("repos"), list) or not config["repos"]:
        not_passed(".pre-commit-config.yaml: no repos configured")

    hooks = _all_hooks(config)
    hook_ids = {h.get("id") for h in hooks}
    missing = REQUIRED_HOOK_IDS - hook_ids
    if missing:
        not_passed(f".pre-commit-config.yaml: missing required hook id(s): {sorted(missing)}")

    mypy_hook = next((h for h in hooks if h.get("id") == "mypy"), None)
    mypy_args = (mypy_hook or {}).get("args") or []
    if "--strict" not in mypy_args:
        not_passed(
            ".pre-commit-config.yaml: the mypy hook must pass --strict in its args"
        )


def _prep_scratch_repo(scratch: Path, fixture_dir: Path) -> Path:
    repo = scratch / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, repo / "statkit")
    shutil.copy(CONFIG_PATH, repo / ".pre-commit-config.yaml")

    def git(*args: str) -> subprocess.CompletedProcess:
        return run(["git", *args], cwd=repo)

    git("init", "-q")
    git("config", "user.email", "validator@example.com")
    git("config", "user.name", "validator")
    add = git("add", "-A")
    if add.returncode != 0:
        not_passed(f"scratch git add failed: {add.stderr.strip()}")
    return repo


def _run_pre_commit(repo: Path) -> subprocess.CompletedProcess:
    return run(["pre-commit", "run", "--all-files"], cwd=repo, timeout=600)


@guarded
def main() -> None:
    _check_structure()

    scratch = fresh_scratch_dir(TASK_DIR)
    try:
        clean_repo = _prep_scratch_repo(scratch / "clean", FIXTURES_CLEAN)
        clean_result = _run_pre_commit(clean_repo)
        if clean_result.returncode != 0:
            excerpt = "\n".join((clean_result.stdout or "").strip().splitlines()[-20:])
            not_passed(
                "pre-commit run --all-files failed on the CLEAN fixture — it should "
                f"pass with no changes needed. Output:\n{excerpt}"
            )

        bad_repo = _prep_scratch_repo(scratch / "bad", FIXTURES_BAD)
        bad_result = _run_pre_commit(bad_repo)
        if bad_result.returncode == 0:
            not_passed(
                "pre-commit run --all-files unexpectedly PASSED on the BAD fixture — "
                "your hooks did not catch the planted problems"
            )
        if "Failed" not in (bad_result.stdout or ""):
            not_passed(
                "pre-commit run --all-files exited nonzero on the BAD fixture, but no "
                "hook reported 'Failed' — check the config isn't erroring out for an "
                "unrelated reason"
            )
    finally:
        cleanup_scratch(scratch)

    passed("clean fixture passes pre-commit, bad fixture is caught by it")


if __name__ == "__main__":
    main()
