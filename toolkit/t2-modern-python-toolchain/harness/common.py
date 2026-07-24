"""Shared pass/fail plumbing and subprocess/config helpers for toolkit t2
validators.

Convention (matches the rest of the repo): a validator prints exactly one
line and exits. On success: `PASSED` (optionally with a trailing detail
line). On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.

Every task in this module is graded behaviorally — by shelling out to the
real tool (uv, ruff, mypy, pre-commit) and checking its exit code and
output — plus a handful of structural checks that parse the learner's own
config so a passing tool run can't be faked by disabling every rule.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
import tomllib
import traceback
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

F = TypeVar("F", bound=Callable[..., None])


# --------------------------------------------------------------------------
# Pass / fail plumbing
# --------------------------------------------------------------------------

def not_passed(reason: str) -> NoReturn:
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg: str = "") -> None:
    print(f"PASSED{': ' + msg if msg else ''}")


def _last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line:
            return line
    return "(no error message)"


def guarded(fn: F) -> Callable[..., None]:
    """Wrap a validator's entry point so any uncaught exception becomes a
    single NOT PASSED line instead of a raw traceback.

    Usage:
        @guarded
        def main() -> None:
            ...
            passed()

        if __name__ == "__main__":
            main()
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - intentional catch-all
            text = "".join(traceback.format_exception_only(type(exc), exc))
            not_passed(_last_line(text))

    return wrapper


# --------------------------------------------------------------------------
# Subprocess helpers
# --------------------------------------------------------------------------

def run(
    cmd: list[str],
    cwd: Path | str | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, never raising on a nonzero exit — the caller decides
    what a given exit code means for the check at hand."""
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as e:
        not_passed(f"command not found: {cmd[0]} ({e})")
    except subprocess.TimeoutExpired:
        not_passed(f"command timed out after {timeout}s: {' '.join(cmd)}")


def _tail(text: str, n: int = 25) -> str:
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n:])


def require_success(result: subprocess.CompletedProcess, action: str) -> None:
    """Fail with a trimmed excerpt of the command's own output if it did
    not exit 0. Never leaks the full output — just enough to orient."""
    if result.returncode != 0:
        detail = _tail(result.stderr) or _tail(result.stdout) or "(no output)"
        not_passed(f"{action} failed (exit {result.returncode}): {detail}")


def require_failure(result: subprocess.CompletedProcess, action: str) -> None:
    """Fail if a command that was expected to catch a problem exited 0
    instead — i.e. the check we relied on did not actually fire."""
    if result.returncode == 0:
        not_passed(f"{action} unexpectedly succeeded — it should have failed")


# --------------------------------------------------------------------------
# Config parsing
# --------------------------------------------------------------------------

def load_toml(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        not_passed(f"expected file not found: {p}")
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        not_passed(f"{p} is not valid TOML: {e}")


def load_yaml(path: Path) -> dict:
    import yaml

    p = Path(path)
    if not p.exists():
        not_passed(f"expected file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        not_passed(f"{p} is not valid YAML: {e}")
    if not isinstance(data, dict):
        not_passed(f"{p} must contain a YAML mapping at the top level")
    return data


# --------------------------------------------------------------------------
# Source inspection
# --------------------------------------------------------------------------

def count_pattern(paths: list[Path], pattern: str) -> int:
    """Count regex matches for `pattern` across a list of source files.
    Used to cap blanket-suppression escape hatches (# noqa, # type: ignore)
    so a task can't be "solved" by silencing every check."""
    regex = re.compile(pattern)
    total = 0
    for p in paths:
        p = Path(p)
        if p.exists():
            total += len(regex.findall(p.read_text(encoding="utf-8")))
    return total


def iter_py_files(root: Path) -> list[Path]:
    return sorted(Path(root).rglob("*.py"))


# --------------------------------------------------------------------------
# Scratch directories
# --------------------------------------------------------------------------

def _rmtree_onerror(func, path, exc_info) -> None:
    """Windows leaves files (notably inside a throwaway repo's .git/) as
    read-only; retry once after clearing that bit before giving up."""
    import os
    import stat

    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, onerror=_rmtree_onerror)


def fresh_scratch_dir(task_dir: Path, name: str = "scratch") -> Path:
    """Return an empty `task_dir/name` directory, wiping any leftovers from
    a previous, interrupted run. Callers are responsible for removing it
    again when done (see `cleanup_scratch`)."""
    scratch = Path(task_dir) / name
    if scratch.exists():
        _rmtree(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def cleanup_scratch(scratch: Path) -> None:
    if Path(scratch).exists():
        _rmtree(scratch)
