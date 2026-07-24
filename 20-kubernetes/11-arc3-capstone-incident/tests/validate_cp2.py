"""CP2 validator for task 11 (Arc 3 capstone) -- incident writeup + green
re-run of CP1.

Checks `INCIDENT.md` is filled in (all five required section headings
present, each with real content beyond the shipped '[fill in' placeholder,
a minimum length per section, and this incident's own vocabulary --
ConfigMap/envFrom/REQUIRED_ENV/CrashLoopBackOff -- not generic incident-
response prose), THEN re-runs validate_cp1.py as a SUBPROCESS and requires
it to exit 0. A writeup describing a fix that no longer actually restores
the cluster does not pass this checkpoint either.

The subprocess timeout below is a GENEROUS OUTER SAFETY WRAPPER, not a
performance gate -- CP1 seeds a live incident, waits on real rollouts, a
draining window, and a scale-to-zero durability check, so it gets a large
one. It does not make a wall-clock assertion of its own.

Run from this task directory:

    uv run python tests/validate_cp2.py
"""

import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import _last_line, check_sections, guarded, not_passed, passed  # noqa: E402

INCIDENT_PATH = TASK_ROOT / "INCIDENT.md"

REQUIRED_SECTIONS = [
    "Symptoms observed",
    "Root cause",
    "Cascade chain",
    "How I localized it",
    "Prevention",
]

MIN_CHARS = 200

REQUIRED_KEYWORDS = ["ConfigMap", "envFrom", "REQUIRED_ENV", "CrashLoopBackOff"]
MIN_KEYWORD_HITS = 3

CP1_TIMEOUT = 600  # generous safety wrapper -- live seed + fix + durability check


def _check_incident_doc():
    sections = check_sections(INCIDENT_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    text = INCIDENT_PATH.read_text(encoding="utf-8")
    hits = [kw for kw in REQUIRED_KEYWORDS if kw in text]
    if len(hits) < MIN_KEYWORD_HITS:
        not_passed(
            f"INCIDENT.md only grounds itself in {len(hits)}/{MIN_KEYWORD_HITS} required concept(s) "
            f"among {REQUIRED_KEYWORDS} (matched: {hits}) -- this needs to name this incident's own "
            "objects/fields, not generic incident-response prose"
        )
    return sections, hits


def _run_cp1():
    script = TASK_ROOT / "tests" / "validate_cp1.py"
    try:
        return subprocess.run(
            ["uv", "run", "python", str(script)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=CP1_TIMEOUT,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"validate_cp1.py did not exit within {CP1_TIMEOUT}s (generous safety wrapper -- likely a hang)")


@guarded
def main():
    sections, hits = _check_incident_doc()

    result = _run_cp1()
    if result.returncode != 0:
        not_passed(
            f"CP1 no longer passes -- fix the pipeline before finishing the writeup: "
            f"{_last_line(result.stdout or result.stderr)}"
        )

    passed(f"INCIDENT.md filled ({len(sections)} sections, grounded concepts: {hits}); CP1 still passes")


if __name__ == "__main__":
    main()
