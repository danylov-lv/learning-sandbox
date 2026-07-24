"""Shared pass/fail plumbing and process/data helpers for module t3
(CLI data toolkit) validators.

Convention (matches the rest of the repo, copied from
17-system-design/harness/common.py): a validator prints exactly one line
and exits. On success: `PASSED` (optionally with a trailing detail line).
On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.

Every task here is an EXPECTED-OUTPUT check: run the learner's script,
parse what it printed (or the files it wrote), and diff that against a
ground truth the validator computes independently in Python (pandas /
numpy / duckdb-python / stdlib re+pathlib) -- never by re-running the
learner's own command with different flags and trusting agreement.
"""

from __future__ import annotations

import functools
import json
import math
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

F = TypeVar("F", bound=Callable[..., None])

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to 17-system-design)
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
# Data fixtures
# --------------------------------------------------------------------------

def require_data(*relative_parts: str) -> Path:
    """Path under data/, or NOT PASSED with a `generate.py` hint if missing."""
    p = DATA_DIR.joinpath(*relative_parts)
    if not p.exists():
        not_passed(
            f"fixture not found: {p} -- run `uv run python generate.py` "
            "from the module root first"
        )
    return p


# --------------------------------------------------------------------------
# Running the learner's script
# --------------------------------------------------------------------------

def _bash_executable() -> str:
    """Resolve the bash to run learner scripts with.

    On Windows, letting subprocess/CreateProcess search PATH for a bare
    "bash" can land on the WSL launcher stub in System32 (which precedes
    PATH entries in Windows' search order) instead of Git Bash, and that
    stub cannot resolve a D:/... path. shutil.which() walks PATH itself
    and finds Git Bash correctly, so resolve explicitly instead of
    trusting subprocess's own lookup.
    """
    found = shutil.which("bash")
    return found or "bash"


def run_script(path, args: list | None = None, cwd=None, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Run the learner's script (`bash <path> [args...]`) and return the
    completed process (stdout/stderr captured as text, never raises on a
    non-zero exit -- callers decide what a bad exit code means)."""
    p = Path(path)
    if not p.exists():
        not_passed(f"script not found: {p}")
    cmd = [_bash_executable(), p.as_posix(), *(args or [])]
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        not_passed(f"{p.name} timed out after {timeout:.0f}s -- still the stock stub, or stuck?")


def require_success(result: subprocess.CompletedProcess, label: str = "script") -> None:
    if result.returncode != 0:
        tail = _last_line(result.stderr) or _last_line(result.stdout)
        not_passed(f"{label} exited {result.returncode}: {tail}")


def parse_marker_sections(text: str, labels: list) -> dict:
    """Split stdout on `===LABEL===` marker lines into {label: body_text}.

    Every label in `labels` must appear exactly once, in any order; extra
    unlabeled leading text (before the first marker) is ignored. Each
    body is the raw text between its marker and the next one (or EOF),
    with surrounding blank lines stripped but internal lines untouched.
    """
    pattern = "^===(" + "|".join(re.escape(l) for l in labels) + r")===[ \t]*$"
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if not matches:
        not_passed(f"no ===LABEL=== markers found in stdout (expected: {', '.join(labels)})")

    sections = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in sections:
            not_passed(f"marker '==={label}===' appears more than once in stdout")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[label] = text[start:end].strip("\n")

    missing = [l for l in labels if l not in sections]
    if missing:
        not_passed(f"missing marker(s) in stdout: {', '.join('===' + l + '===' for l in missing)}")

    return sections


def parse_json_stdout(result: subprocess.CompletedProcess, label: str = "script"):
    text = (result.stdout or "").strip()
    if not text:
        not_passed(f"{label} printed no stdout")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        not_passed(f"{label} stdout is not valid JSON: {e}")


# --------------------------------------------------------------------------
# Numeric / structural comparison
# --------------------------------------------------------------------------

def check_close(actual, expected, rel_tol: float = 1e-6, abs_tol: float = 1e-6, label: str = "value") -> None:
    if actual is None or isinstance(actual, bool) or not isinstance(actual, (int, float)):
        not_passed(f"{label}: expected a number, got {actual!r}")
    if isinstance(actual, float) and math.isnan(actual):
        not_passed(f"{label}: got NaN, expected {expected!r}")
    if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol):
        not_passed(f"{label}: got {actual!r}, expected {expected!r} (rel_tol={rel_tol})")


def _round_floats(obj, ndigits: int = 6):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def check_json_equal(actual, expected, label: str = "output", ndigits: int = 6) -> None:
    """Deep-equal comparison with float rounding (so 83.209999999 and 83.21
    agree). Caller is responsible for sorting lists into a canonical order
    first when the task is order-insensitive."""
    a = _round_floats(actual, ndigits)
    e = _round_floats(expected, ndigits)
    if a != e:
        not_passed(f"{label} does not match expected output.\n  got:      {a!r}\n  expected: {e!r}")
