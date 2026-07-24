"""Validator for 03-typing-strict. Run from the module root:

    cd toolkit/t2-modern-python-toolchain
    uv run python 03-typing-strict/tests/validate.py

Checks, in order:
  1. project/pyproject.toml's [tool.mypy] structurally sets `strict = true`.
  2. `mypy src` (reading that config) exits 0.
  3. `pytest -q` still passes against the given, unedited test suite — the
     fix must preserve behavior, not just satisfy the type checker by
     gutting the implementation.
  4. `# type: ignore` usage under src/ is capped at 0 — every planted
     issue in this task is cleanly fixable without one.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    count_pattern,
    guarded,
    iter_py_files,
    load_toml,
    not_passed,
    passed,
    require_success,
    run,
)

PROJECT_DIR = TASK_DIR / "project"
SRC_DIR = PROJECT_DIR / "src"
TYPE_IGNORE_CAP = 0


@guarded
def main() -> None:
    pyproject_path = PROJECT_DIR / "pyproject.toml"
    config = load_toml(pyproject_path)
    mypy_cfg = config.get("tool", {}).get("mypy", {})

    if mypy_cfg.get("strict") is not True:
        not_passed(
            "project/pyproject.toml: [tool.mypy].strict must be set to true "
            f"(got {mypy_cfg.get('strict')!r})"
        )

    mypy_result = run(["mypy", "src"], cwd=PROJECT_DIR)
    require_success(mypy_result, "mypy src")

    pytest_result = run(["pytest", "-q"], cwd=PROJECT_DIR)
    require_success(pytest_result, "pytest -q (given, unedited test suite)")

    ignore_count = count_pattern(iter_py_files(SRC_DIR), r"#\s*type:\s*ignore")
    if ignore_count > TYPE_IGNORE_CAP:
        not_passed(
            f"found {ignore_count} '# type: ignore' comment(s) under src/, cap is "
            f"{TYPE_IGNORE_CAP} — fix the underlying typing issues instead of "
            "silencing them"
        )

    passed("mypy --strict config confirmed, mypy src clean, pytest green, no type: ignore")


if __name__ == "__main__":
    main()
