"""Validator for 05-packaging-internal-library. Run from the module root:

    cd toolkit/t2-modern-python-toolchain
    uv run python 05-packaging-internal-library/tests/validate.py

Checks, in order:
  1. Structural: project/src/pricelib/ exists (src layout), no stray
     project/pricelib/ (flat layout) sits alongside it.
  2. project/pyproject.toml declares a real [build-system] (hatchling or
     uv_build), a [project].version matching the package's own
     __version__, and a `pricelib` console script mapped to
     `pricelib.cli:main`.
  3. `uv build` succeeds and produces both a wheel and an sdist under
     project/dist/.
  4. The wheel installs cleanly into a throwaway venv, and the installed
     `pricelib` console script prints the expected summary line.
  5. dist/ and the throwaway venv are removed afterward either way.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    cleanup_scratch,
    fresh_scratch_dir,
    guarded,
    load_toml,
    not_passed,
    passed,
    require_success,
    run,
)

PROJECT_DIR = TASK_DIR / "project"
SRC_PKG_DIR = PROJECT_DIR / "src" / "pricelib"
STRAY_FLAT_DIR = PROJECT_DIR / "pricelib"
DIST_DIR = PROJECT_DIR / "dist"

ENTRY_POINT = "pricelib"
ENTRY_TARGET = "pricelib.cli:main"

SAMPLE_PRICES = [12.5, 7.25, 30.0, 4.99]
EXPECTED_COUNT = len(SAMPLE_PRICES)
EXPECTED_AVG = sum(SAMPLE_PRICES) / len(SAMPLE_PRICES)

VALID_BACKENDS = ("hatchling.build", "uv_build")


def _package_version() -> str:
    init_py = SRC_PKG_DIR / "__init__.py"
    if not init_py.exists():
        not_passed(f"expected file not found: {init_py}")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init_py.read_text(encoding="utf-8"))
    if not m:
        not_passed(f"could not find __version__ in {init_py}")
    return m.group(1)


def _check_structure() -> None:
    if not SRC_PKG_DIR.is_dir():
        not_passed("project/src/pricelib/ not found — this task uses a src layout")
    if STRAY_FLAT_DIR.exists():
        not_passed(
            "project/pricelib/ exists alongside project/src/pricelib/ — this task "
            "requires a clean src layout, not a flat one"
        )


def _check_pyproject() -> None:
    config = load_toml(PROJECT_DIR / "pyproject.toml")
    project = config.get("project", {})

    build_system = config.get("build-system", {})
    backend = build_system.get("build-backend")
    if backend not in VALID_BACKENDS:
        not_passed(
            f"project/pyproject.toml: [build-system].build-backend must be one of "
            f"{VALID_BACKENDS} (got {backend!r})"
        )

    version = project.get("version")
    expected_version = _package_version()
    if not version:
        not_passed("project/pyproject.toml: [project].version is missing")
    if version != expected_version:
        not_passed(
            f"project/pyproject.toml: [project].version is {version!r}, but "
            f"src/pricelib/__init__.py says __version__ = {expected_version!r} — "
            "they must match"
        )

    scripts = project.get("scripts", {})
    if scripts.get(ENTRY_POINT) != ENTRY_TARGET:
        not_passed(
            f"project/pyproject.toml: [project.scripts] must map '{ENTRY_POINT}' to "
            f"'{ENTRY_TARGET}' (got: {scripts.get(ENTRY_POINT)!r})"
        )


def _check_output(text: str) -> None:
    m = re.search(r"pricelib\s+(\S+):\s*count=(\d+)\s+avg=([\d.]+)", text)
    if not m:
        not_passed(
            f"installed console script output did not match the expected shape: {text!r}"
        )
    version, count, avg = m.groups()
    expected_version = _package_version()
    if version != expected_version:
        not_passed(f"console script printed version {version!r}, expected {expected_version!r}")
    if int(count) != EXPECTED_COUNT:
        not_passed(f"console script printed count={count}, expected {EXPECTED_COUNT}")
    if abs(float(avg) - EXPECTED_AVG) > 0.01:
        not_passed(f"console script printed avg={avg}, expected {EXPECTED_AVG:.2f}")


@guarded
def main() -> None:
    _check_structure()
    _check_pyproject()

    scratch = fresh_scratch_dir(TASK_DIR)
    try:
        build_result = run(["uv", "build", "--out-dir", str(DIST_DIR)], cwd=PROJECT_DIR)
        require_success(build_result, "uv build")

        wheels = sorted(DIST_DIR.glob("*.whl"))
        sdists = sorted(DIST_DIR.glob("*.tar.gz"))
        if not wheels:
            not_passed("uv build did not produce a .whl under project/dist/")
        if not sdists:
            not_passed("uv build did not produce a sdist (.tar.gz) under project/dist/")

        venv_dir = scratch / "venv"
        venv_result = run(["uv", "venv", str(venv_dir)], cwd=PROJECT_DIR)
        require_success(venv_result, "uv venv (throwaway install target)")

        install_result = run(
            ["uv", "pip", "install", "--python", str(venv_dir), str(wheels[-1])],
            cwd=PROJECT_DIR,
        )
        require_success(install_result, f"uv pip install {wheels[-1].name}")

        script_win = venv_dir / "Scripts" / f"{ENTRY_POINT}.exe"
        script_posix = venv_dir / "bin" / ENTRY_POINT
        script_path = script_win if script_win.exists() else script_posix
        if not script_path.exists():
            not_passed(
                f"installed console script not found at {script_win} or {script_posix} — "
                "check the entry point name and target"
            )

        run_result = run([str(script_path)], cwd=PROJECT_DIR)
        require_success(run_result, f"running installed console script {script_path.name}")
        _check_output(run_result.stdout)
    finally:
        cleanup_scratch(scratch)
        if DIST_DIR.exists():
            cleanup_scratch(DIST_DIR)

    passed("src layout, build-system/version/entry-point config, uv build, and installed script all checked")


if __name__ == "__main__":
    main()
