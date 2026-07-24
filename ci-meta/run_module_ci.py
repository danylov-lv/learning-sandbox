"""Per-module CI: verify the authoring contract for one changed module.

Usage: python run_module_ci.py <module-id>

Checks applied, in order:
  1. required scaffold files present (checks.check_required_files)
  2. no reference solution leaked (checks.check_no_solution)
  3. python modules only: `uv lock --check` (lock matches pyproject)
  4. services == light: docker compose up --wait, then always tear down;
     services == heavy: skip live step, emit an ::notice:: with the reason;
     services == none: no service step.

This intentionally never runs the module's own task validators -- those
fail by design on unsolved stubs. See ci-meta/README.md for why.

Uses stdlib + subprocess (uv, docker) only -- no third-party imports.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402
import registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _notice(msg: str) -> None:
    print(f"::notice::{msg}")


def _error(msg: str) -> None:
    print(f"::error::{msg}")


def _uv_lock_check(module_dir: Path) -> tuple[bool, str]:
    if shutil.which("uv") is None:
        _notice("uv not found on PATH; skipping `uv lock --check` (would run in CI)")
        return True, "skipped (uv not available locally)"
    result = subprocess.run(
        ["uv", "lock", "--check"], cwd=module_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = detail[-1] if detail else "uv lock --check failed"
        return False, f"uv.lock is out of date with pyproject.toml: {reason}"
    return True, "ok"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True,
    )
    return result.returncode == 0


def _run_light_services(module_dir: Path, module_id: str) -> tuple[bool, str]:
    compose_file = module_dir / "docker-compose.yml"
    if not compose_file.is_file():
        return False, f"{module_id} is classified light but has no docker-compose.yml"

    if not _docker_available():
        _notice(
            f"docker not available locally; skipping live service boot for "
            f"{module_id} (would run `docker compose up -d --wait` in CI)"
        )
        return True, "skipped (docker not available locally)"

    up = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
        cwd=module_dir, capture_output=True, text=True,
    )
    try:
        if up.returncode != 0:
            detail = (up.stderr or up.stdout).strip().splitlines()
            reason = detail[-1] if detail else "docker compose up --wait failed"
            return False, f"service containers did not reach healthy: {reason}"
        return True, "service containers reached healthy"
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down", "-v"],
            cwd=module_dir, capture_output=True, text=True,
        )


def run(module_id: str) -> tuple[bool, str]:
    try:
        entry = registry.get(module_id)
    except KeyError as exc:
        return False, str(exc)

    module_dir = REPO_ROOT / entry.path

    ok, reason = checks.check_required_files(module_id)
    if not ok:
        return False, f"required-files check failed: {reason}"

    ok, reason = checks.check_no_solution(module_id)
    if not ok:
        return False, f"no-solution check failed: {reason}"

    if entry.kind == "python":
        ok, reason = _uv_lock_check(module_dir)
        if not ok:
            return False, reason

    if entry.services == "light":
        ok, reason = _run_light_services(module_dir, module_id)
        if not ok:
            return False, reason
    elif entry.services == "heavy":
        _notice(f"live service tests skipped for {module_id}: {entry.note}")
    # services == "none": nothing to do

    return True, "ok"


def main() -> int:
    if len(sys.argv) != 2:
        print("NOT PASSED: usage: python run_module_ci.py <module-id>")
        return 1

    module_id = sys.argv[1]
    ok, reason = run(module_id)
    if ok:
        print("PASSED")
        return 0
    _error(f"{module_id}: {reason}")
    print(f"NOT PASSED: {reason}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"NOT PASSED: {exc}")
        sys.exit(1)
