"""Runs validate_cp1, validate_cp2 and validate_cp3 in sequence, each as a
fresh subprocess, and reports which checkpoint failed first.

This is a thin convenience wrapper -- CP3 already re-runs CP1 and CP2
internally, so this script's only job is to report progress for all
three checkpoints in one command instead of three.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import _last_line, guarded, not_passed, passed  # noqa: E402

CHECKPOINTS = ["validate_cp1.py", "validate_cp2.py", "validate_cp3.py"]


def _run(name: str) -> None:
    script = TASK_ROOT / "tests" / name
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(TASK_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        detail = _last_line(proc.stdout + proc.stderr)
        detail = detail[len("NOT PASSED: "):] if detail.startswith("NOT PASSED: ") else detail
        not_passed(f"{name} failed: {detail}")


@guarded
def main() -> None:
    for name in CHECKPOINTS:
        _run(name)
    passed("CP1 + CP2 + CP3 all green")


if __name__ == "__main__":
    main()
