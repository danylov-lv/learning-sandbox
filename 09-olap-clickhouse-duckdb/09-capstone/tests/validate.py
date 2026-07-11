"""Runner for the s09 capstone -- invokes validate_cp1, validate_cp2, and
validate_cp3 in order (each as a subprocess) and prints a summary of which
checkpoints passed.

This is a convenience wrapper, not a fourth checkpoint: completion criteria
is "all three green", which running each validator individually also
proves. Note validate_cp3.py itself re-runs CP1 and CP2 as part of its own
check, so running this full sequence exercises CP1/CP2 more than once --
that overlap is intentional (CP3's re-run guards against regressions
introduced while writing the memo).

Run from this task's directory:

    uv run python tests/validate.py
"""

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, passed  # noqa: E402

CHECKPOINTS = ["validate_cp1.py", "validate_cp2.py", "validate_cp3.py"]
TIMEOUT = 600


def _last_line(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _run(name):
    script = TASK_ROOT / "tests" / name
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(script)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        return result.returncode == 0, _last_line(result.stdout or result.stderr)
    except FileNotFoundError:
        return False, "uv not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"did not exit within {TIMEOUT}s"


@guarded
def main():
    results = []
    for name in CHECKPOINTS:
        ok, detail = _run(name)
        results.append((name, ok, detail))
        status = "PASSED" if ok else "NOT PASSED"
        print(f"{name}: {status} -- {detail}")

    n_passed = sum(1 for _, ok, _ in results if ok)
    summary = ", ".join(f"{name}={'ok' if ok else 'FAIL'}" for name, ok, _ in results)

    if n_passed < len(results):
        print(f"NOT PASSED: {n_passed}/{len(results)} checkpoints green ({summary})")
        sys.exit(1)

    passed(f"all {len(results)} checkpoints green ({summary})")


if __name__ == "__main__":
    main()
