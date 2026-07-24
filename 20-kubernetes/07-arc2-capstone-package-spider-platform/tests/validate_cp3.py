"""CP3 validator for task 07 (Arc 2 capstone) -- design review + green re-run.

Checks `DESIGN.md` is filled in (all five required section headings
present, each with real content beyond the shipped '[fill in' placeholder,
a minimum length per section, mentions "checksum" and "fullname", and
names at least 3 real `values.yaml` paths from this chart's actual
contract -- not generic Helm prose), THEN re-runs `validate_cp1.py` and, if
that passes, `validate_cp2.py` as SUBPROCESSES and requires both to exit
0. A design memo for a chart that no longer lints, or that regressed on
CP2's live upgrade behavior, does not pass this checkpoint either.

The subprocess timeouts below are GENEROUS OUTER SAFETY WRAPPERS, not
performance gates -- CP1 is offline and fast; CP2 installs into a live
cluster and waits on real rollouts, so it gets a larger one. Neither makes
a wall-clock assertion of its own.

Run from this task directory:

    uv run python tests/validate_cp3.py
"""

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import _last_line, check_sections, guarded, not_passed, passed  # noqa: E402

DESIGN_PATH = TASK_ROOT / "DESIGN.md"

REQUIRED_SECTIONS = [
    "What is a value and why",
    "What stays hardcoded and why",
    "Upgrade story",
    "Failure modes",
    "If this ran in production",
]

MIN_CHARS = 220

# Real values.yaml paths from this chart's own contract (README.md "Chart
# contract") -- the design doc must ground its "what is a value" argument
# in at least 3 of these, not generic Helm advice.
KNOWN_VALUE_PATHS = [
    "workers.replicas",
    "workers.resources",
    "workers.processMs",
    "workers.probes",
    "producer.ratePerS",
    "producer.enabled",
    "producer.replicas",
    "target.enabled",
    "target.replicas",
    "queue.key",
    "queue.port",
]

REQUIRED_KEYWORDS = ["checksum", "fullname"]

CP1_TIMEOUT = 120
CP2_TIMEOUT = 600  # generous safety wrapper -- live install + rollouts + upgrade


def check_design_doc():
    sections = check_sections(DESIGN_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    text = DESIGN_PATH.read_text(encoding="utf-8")
    lower = text.lower()

    missing_kw = [kw for kw in REQUIRED_KEYWORDS if kw not in lower]
    if missing_kw:
        not_passed(f"DESIGN.md doesn't mention required concept(s): {missing_kw}")

    hit_paths = [p for p in KNOWN_VALUE_PATHS if p in text]
    if len(hit_paths) < 3:
        not_passed(
            f"DESIGN.md names only {len(hit_paths)} real values.yaml path(s) ({hit_paths}); "
            f"needs at least 3 from this chart's actual values contract, e.g. {KNOWN_VALUE_PATHS[:4]}"
        )

    return sections, hit_paths


def _run_validator(name, timeout):
    script = TASK_ROOT / "tests" / name
    try:
        return subprocess.run(
            ["uv", "run", "python", str(script)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"{name} did not exit within {timeout}s (generous safety wrapper -- likely a hang, not slowness)")


@guarded
def main():
    sections, hit_paths = check_design_doc()

    r1 = _run_validator("validate_cp1.py", CP1_TIMEOUT)
    if r1.returncode != 0:
        not_passed(
            f"CP1 no longer passes -- fix chart/ before finishing the design review: "
            f"{_last_line(r1.stdout or r1.stderr)}"
        )

    r2 = _run_validator("validate_cp2.py", CP2_TIMEOUT)
    if r2.returncode != 0:
        not_passed(
            f"CP2 no longer passes -- fix chart/ before finishing the design review: "
            f"{_last_line(r2.stdout or r2.stderr)}"
        )

    passed(
        f"DESIGN.md filled ({len(sections)} sections, named values paths: {hit_paths}); "
        "CP1 and CP2 both still pass"
    )


if __name__ == "__main__":
    main()
