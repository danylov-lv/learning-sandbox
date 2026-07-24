"""Validator for 01-uv-project-management. Run from the module root:

    cd toolkit/t2-modern-python-toolchain
    uv run python 01-uv-project-management/tests/validate.py

Checks, in order:
  1. project/pyproject.toml declares the pyyaml dependency, the `pricetool`
     console script, and a `dev` dependency group containing pytest
     (structural — parsed straight from the TOML, not inferred from tool
     output).
  2. `uv sync` succeeds in project/ and produces a uv.lock.
  3. `uv lock --check` confirms the lockfile is consistent with
     pyproject.toml.
  4. `uv run pricetool` produces the expected summary line.
  5. `uv run pytest -q` passes (proves the dev group actually resolves).
  6. `uv tool run --from . pricetool` produces the same summary line — the
     uv-as-tool-manager path (equivalent to `uvx --from . pricetool`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    load_toml,
    not_passed,
    passed,
    require_success,
    run,
)

PROJECT_DIR = TASK_DIR / "project"
ENTRY_POINT = "pricetool"
ENTRY_TARGET = "pricetool.cli:main"

PRICES = [19.99, 5.50, 42.00, 13.25, 8.75]
EXPECTED_COUNT = len(PRICES)
EXPECTED_MIN = min(PRICES)
EXPECTED_MAX = max(PRICES)
EXPECTED_AVG = sum(PRICES) / len(PRICES)
EXPECTED_CURRENCY = "USD"

OUTPUT_RE = re.compile(
    r"count=(\d+)\s+min=([\d.]+)\s+max=([\d.]+)\s+avg=([\d.]+)\s+currency=(\S+)"
)


def _check_output(text: str, label: str) -> None:
    m = OUTPUT_RE.search(text)
    if not m:
        not_passed(
            f"{label}: output did not match the expected "
            f"'count=... min=... max=... avg=... currency=...' shape: {text!r}"
        )
    count, mn, mx, avg, currency = m.groups()
    if int(count) != EXPECTED_COUNT:
        not_passed(f"{label}: count={count}, expected {EXPECTED_COUNT}")
    if abs(float(mn) - EXPECTED_MIN) > 0.01:
        not_passed(f"{label}: min={mn}, expected {EXPECTED_MIN:.2f}")
    if abs(float(mx) - EXPECTED_MAX) > 0.01:
        not_passed(f"{label}: max={mx}, expected {EXPECTED_MAX:.2f}")
    if abs(float(avg) - EXPECTED_AVG) > 0.01:
        not_passed(f"{label}: avg={avg}, expected {EXPECTED_AVG:.2f}")
    if currency != EXPECTED_CURRENCY:
        not_passed(f"{label}: currency={currency}, expected {EXPECTED_CURRENCY}")


@guarded
def main() -> None:
    pyproject_path = PROJECT_DIR / "pyproject.toml"
    config = load_toml(pyproject_path)
    project = config.get("project", {})

    deps = project.get("dependencies", [])
    if not any(re.match(r"(?i)^pyyaml\b", d) for d in deps):
        not_passed(
            "project/pyproject.toml: [project].dependencies must include pyyaml "
            "(pricetool.cli imports it)"
        )

    scripts = project.get("scripts", {})
    if scripts.get(ENTRY_POINT) != ENTRY_TARGET:
        not_passed(
            f"project/pyproject.toml: [project.scripts] must map "
            f"'{ENTRY_POINT}' to '{ENTRY_TARGET}' (got: {scripts.get(ENTRY_POINT)!r})"
        )

    dev_group = config.get("dependency-groups", {}).get("dev", [])
    if not any(re.match(r"(?i)^pytest\b", d) for d in dev_group):
        not_passed(
            "project/pyproject.toml: [dependency-groups].dev must include pytest"
        )

    sync = run(["uv", "sync"], cwd=PROJECT_DIR)
    require_success(sync, "uv sync")

    lock_path = PROJECT_DIR / "uv.lock"
    if not lock_path.exists():
        not_passed("uv sync ran but did not produce project/uv.lock")

    lock_check = run(["uv", "lock", "--check"], cwd=PROJECT_DIR)
    require_success(
        lock_check, "uv lock --check (uv.lock must be consistent with pyproject.toml)"
    )

    run_result = run(["uv", "run", ENTRY_POINT], cwd=PROJECT_DIR)
    require_success(run_result, f"uv run {ENTRY_POINT}")
    _check_output(run_result.stdout, f"uv run {ENTRY_POINT}")

    test_result = run(["uv", "run", "pytest", "-q"], cwd=PROJECT_DIR)
    require_success(test_result, "uv run pytest -q (dev dependency group)")

    tool_result = run(["uv", "tool", "run", "--from", ".", ENTRY_POINT], cwd=PROJECT_DIR)
    require_success(
        tool_result, f"uv tool run --from . {ENTRY_POINT} (uvx-style tool invocation)"
    )
    _check_output(tool_result.stdout, f"uv tool run --from . {ENTRY_POINT}")

    passed(
        "pyproject.toml config, uv sync, lock consistency, entry point, "
        "dev-group pytest, and uv tool run all checked"
    )


if __name__ == "__main__":
    main()
