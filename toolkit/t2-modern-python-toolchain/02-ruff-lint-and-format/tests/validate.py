"""Validator for 02-ruff-lint-and-format. Run from the module root:

    cd toolkit/t2-modern-python-toolchain
    uv run python 02-ruff-lint-and-format/tests/validate.py

Checks, in order:
  1. project/pyproject.toml's [tool.ruff] / [tool.ruff.lint] structurally
     declares line-length=100, a select list covering E, F, the two
     required non-default families (I, B), and a per-file-ignores entry
     for __init__.py — and does NOT blanket-ignore everything.
  2. `ruff check` exits 0 against the configured project.
  3. `ruff format --check` exits 0 against the configured project.
  4. The planted issues are independently confirmed gone from the source
     (not merely silenced): the stray `sys` import, the bare `except`,
     the mutable default argument, the `== None` comparison, and the
     placeholder-less f-string.
  5. `# noqa` usage is capped — the fixes must be real, not suppressed.
"""

from __future__ import annotations

import re
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

REQUIRED_LINE_LENGTH = 100
REQUIRED_SELECT_PREFIXES = ["E", "F", "I", "B"]
NOQA_CAP = 0


def _lint_config(config: dict) -> dict:
    ruff = config.get("tool", {}).get("ruff", {})
    # Modern ruff config nests lint options under [tool.ruff.lint]; fall
    # back to the top-level table for select/per-file-ignores in case the
    # learner used the older flat schema.
    lint = ruff.get("lint", {})
    return {
        "line-length": ruff.get("line-length"),
        "select": lint.get("select") or ruff.get("select") or [],
        "ignore": lint.get("ignore") or ruff.get("ignore") or [],
        "per-file-ignores": lint.get("per-file-ignores") or ruff.get("per-file-ignores") or {},
    }


@guarded
def main() -> None:
    pyproject_path = PROJECT_DIR / "pyproject.toml"
    config = load_toml(pyproject_path)
    lint_cfg = _lint_config(config)

    if lint_cfg["line-length"] != REQUIRED_LINE_LENGTH:
        not_passed(
            f"project/pyproject.toml: [tool.ruff].line-length must be "
            f"{REQUIRED_LINE_LENGTH} (got {lint_cfg['line-length']!r})"
        )

    select = lint_cfg["select"]
    if not isinstance(select, list) or not select:
        not_passed(
            "project/pyproject.toml: [tool.ruff.lint].select must be an explicit, "
            "non-empty rule list"
        )
    missing_prefixes = [
        prefix
        for prefix in REQUIRED_SELECT_PREFIXES
        if not any(code == prefix or code.startswith(prefix) for code in select)
    ]
    if missing_prefixes:
        not_passed(
            f"project/pyproject.toml: [tool.ruff.lint].select is missing required "
            f"rule prefix(es): {', '.join(missing_prefixes)} (this task requires "
            f"the default E/F families plus I and B enabled explicitly)"
        )

    if any(str(x).upper() == "ALL" for x in select) or any(
        str(x).upper() == "ALL" for x in lint_cfg["ignore"]
    ):
        not_passed(
            "project/pyproject.toml: do not use select=[\"ALL\"] or ignore=[\"ALL\"] "
            "— select the specific rule families this task asks for"
        )

    per_file_ignores = lint_cfg["per-file-ignores"]
    if not isinstance(per_file_ignores, dict) or not per_file_ignores:
        not_passed(
            "project/pyproject.toml: [tool.ruff.lint].per-file-ignores must contain "
            "an entry (the __init__.py re-export pattern needs F401 exempted there, "
            "and nowhere else)"
        )
    init_key = next((k for k in per_file_ignores if "__init__.py" in k), None)
    if init_key is None:
        not_passed(
            "project/pyproject.toml: per-file-ignores has no entry matching __init__.py"
        )
    init_codes = per_file_ignores[init_key]
    if not isinstance(init_codes, list) or "F401" not in init_codes:
        not_passed(
            f"project/pyproject.toml: per-file-ignores[{init_key!r}] must include F401"
        )
    other_files_ignored = [k for k in per_file_ignores if "__init__.py" not in k]
    if other_files_ignored:
        not_passed(
            f"project/pyproject.toml: per-file-ignores also covers "
            f"{other_files_ignored} — keep the exemption scoped to __init__.py only"
        )

    check_result = run(["ruff", "check", "src"], cwd=PROJECT_DIR)
    require_success(check_result, "ruff check src")

    format_result = run(["ruff", "format", "--check", "src"], cwd=PROJECT_DIR)
    require_success(format_result, "ruff format --check src")

    report_py = SRC_DIR / "reportkit" / "report.py"
    if not report_py.exists():
        not_passed(f"expected file not found: {report_py}")
    report_src = report_py.read_text(encoding="utf-8")

    if re.search(r"^\s*import\s+sys\s*$", report_src, re.MULTILINE):
        not_passed("report.py: the unused `import sys` is still present")
    if re.search(r"except\s*:", report_src):
        not_passed("report.py: a bare `except:` is still present")
    if re.search(r"def\s+summarize\([^)]*=\s*(set|list|dict)\(\)", report_src):
        not_passed("report.py: summarize still uses a mutable default argument")
    if re.search(r"==\s*None|None\s*==", report_src):
        not_passed("report.py: a `== None` comparison is still present (use `is None`)")
    if re.search(r'f"[^"{}]*"', report_src) or re.search(r"f'[^'{}]*'", report_src):
        not_passed("report.py: an f-string with no placeholders is still present")

    noqa_count = count_pattern(iter_py_files(SRC_DIR), r"#\s*noqa")
    if noqa_count > NOQA_CAP:
        not_passed(
            f"found {noqa_count} '# noqa' comment(s) under src/, cap is {NOQA_CAP} — "
            "fix the underlying issues instead of silencing them"
        )

    passed("ruff config structure, ruff check, ruff format --check, and planted-issue fixes all confirmed")


if __name__ == "__main__":
    main()
