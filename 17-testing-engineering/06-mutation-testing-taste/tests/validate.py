"""Validator for task 06 -- does NOT call `harness.mutation.grade()`.

Every other task in this module is graded by the custom mutant-bank engine
in `harness/mutation.py`. This task is the exception: it runs the REAL
mutation-testing tool, `cosmic-ray`, against `src/target.py` and grades on
ITS survivor count. See `.authoring/design.md`, section "Mutation tool for
task 06", for the full rationale and the Windows gotcha this file works
around.

The whole cosmic-ray session (generated config, session database, and the
copies of target.py/test_target.py it mutates in place) lives in a
temporary directory that is deleted when this script exits -- nothing is
ever written into the task directory itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

TARGET_SRC = TASK_ROOT / "src" / "target.py"
TEST_SRC = TASK_ROOT / "tests" / "test_target.py"

PER_MUTANT_TIMEOUT = 30.0  # seconds, cosmic-ray's own per-job timeout
SUBPROCESS_TIMEOUT = 600  # seconds, wall-clock budget for each CLI call

# CPython interns/caches every small int from -5 to 256 as a shared
# singleton object, so cosmic-ray's `core/ReplaceComparisonOperator_*_Is`
# and `*_IsNot` operators (e.g. rewriting `x < lo` into `x is lo`) can
# produce genuine equivalent mutants for small-int values: no test can
# observe a difference, because CPython itself makes `is` and `==` agree
# there. These operator families are excluded from grading. See the
# README's "A note on equivalent mutants" and .authoring/design.md.
_EXCLUDED_OPERATOR_SUFFIXES = ("_Is", "_IsNot")


def _excluded(operator_name: str) -> bool:
    return operator_name.endswith(_EXCLUDED_OPERATOR_SUFFIXES)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT
    )


def _tail(proc: subprocess.CompletedProcess, n: int = 2000) -> str:
    return (proc.stdout + proc.stderr)[-n:]


def _cosmic_ray_config(py_exe: str) -> str:
    # Never a bare "python" here: on this machine a bare "python" on PATH
    # resolved to a *different* interpreter than this project's .venv (one
    # without pytest installed), which made cosmic-ray silently report
    # every mutant -- and the unmutated baseline -- as "killed" because the
    # test command itself failed to run at all.
    test_command = f'"{py_exe}" -m pytest test_target.py -q'
    # json.dumps() produces a properly quote-escaped TOML basic string too
    # (TOML basic strings follow the same escaping rules as JSON strings)
    # -- needed because test_command itself contains literal double quotes.
    test_command_toml = json.dumps(test_command)
    return (
        "[cosmic-ray]\n"
        'module-path = "target.py"\n'
        f"timeout = {PER_MUTANT_TIMEOUT}\n"
        f"test-command = {test_command_toml}\n"
        "excluded-modules = []\n"
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "local"\n'
    )


@guarded
def main() -> None:
    if not TEST_SRC.exists():
        not_passed("tests/test_target.py is missing")
    if not TARGET_SRC.exists():
        not_passed("internal error: src/target.py is missing -- contact the task author")

    py_exe = sys.executable.replace("\\", "/")

    with tempfile.TemporaryDirectory(prefix="cosmic-ray-task06-") as tmp:
        work_dir = Path(tmp)
        shutil.copy2(TARGET_SRC, work_dir / "target.py")
        shutil.copy2(TEST_SRC, work_dir / "test_target.py")

        cfg_path = work_dir / "cr.toml"
        cfg_path.write_text(_cosmic_ray_config(py_exe), encoding="utf-8")

        # A failing baseline means the (unmutated) module doesn't even pass
        # its own tests via this exact test-command -- an internal wiring
        # problem, never something the learner's test edits could cause.
        baseline = _run(
            [sys.executable, "-m", "cosmic_ray.cli", "baseline", str(cfg_path)], work_dir
        )
        if baseline.returncode != 0:
            not_passed(
                "internal error: `cosmic-ray baseline` failed against the "
                "unmutated target.py + your tests -- this should always "
                "pass if the test command is wired correctly. Contact the "
                f"task author.\n{_tail(baseline)}"
            )

        session_path = work_dir / "session.sqlite"
        init_proc = _run(
            [sys.executable, "-m", "cosmic_ray.cli", "init", str(cfg_path), str(session_path)],
            work_dir,
        )
        if init_proc.returncode != 0:
            not_passed(f"internal error: `cosmic-ray init` failed.\n{_tail(init_proc)}")

        exec_proc = _run(
            [sys.executable, "-m", "cosmic_ray.cli", "exec", str(cfg_path), str(session_path)],
            work_dir,
        )
        if exec_proc.returncode != 0:
            not_passed(f"internal error: `cosmic-ray exec` failed.\n{_tail(exec_proc)}")

        dump_proc = _run(
            [sys.executable, "-m", "cosmic_ray.cli", "dump", str(session_path)], work_dir
        )
        if dump_proc.returncode != 0:
            not_passed(f"internal error: `cosmic-ray dump` failed.\n{_tail(dump_proc)}")

        total = 0
        excluded = 0
        missing_results = 0
        survivor_count = 0
        survivor_operators: set[str] = set()

        for line in dump_proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            item, result = json.loads(line)
            total += 1
            operator_name = item["mutations"][0]["operator_name"]

            if result is None:
                missing_results += 1
                continue
            if _excluded(operator_name):
                excluded += 1
                continue
            if result.get("test_outcome") == "survived":
                survivor_count += 1
                survivor_operators.add(operator_name)

    if missing_results:
        not_passed(
            f"internal error: {missing_results} of {total} mutant(s) never "
            "produced a result (cosmic-ray exec may not have finished) -- "
            "contact the task author"
        )

    if survivor_count:
        names = ", ".join(sorted(survivor_operators))
        not_passed(
            f"{survivor_count} mutant(s) survived, using operator(s): {names}. "
            "Your suite does not catch these regressions -- run cosmic-ray "
            "yourself (see the README) and read the survivor output to see "
            "which branch or boundary each operator name points at."
        )

    detail = f"cosmic-ray ran {total} mutant(s), 0 survived"
    if excluded:
        detail += (
            f" ({excluded} core/*_Is or *_IsNot equivalent-mutant "
            "candidate(s) excluded from grading, see README)"
        )
    passed(detail)


if __name__ == "__main__":
    main()
