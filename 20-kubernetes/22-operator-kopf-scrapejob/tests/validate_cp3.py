"""CP3 validator for task 22 (kopf ScrapeJob operator) -- design review.

Checks `DESIGN.md` is filled in (five required sections, each with real
content past the shipped `[fill in` marker, a minimum length, and mentions
of this operator's own vocabulary -- not generic controller-pattern
prose), THEN re-runs `validate_cp1.py` and, if that passes,
`validate_cp2.py` as SUBPROCESSES and requires both to exit 0. A design
memo describing an operator that no longer creates/updates/deletes its
child Deployment does not pass this checkpoint either.

The subprocess timeouts below are generous outer safety wrappers, not
performance gates -- both checkpoints install into the live cluster and
wait on real rollouts already bounded by their own `wait_until` calls.

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
    "The reconcile loop, in your own words",
    "Level-triggered vs. edge-triggered",
    "Owner references and garbage collection",
    "Idempotency of reconcile",
    "Where this would break in production",
]

MIN_CHARS = 220

# Vocabulary this operator's own contract actually uses (README.md /
# operator.py) -- grounds the design doc in what was actually built
# instead of generic controller-pattern prose copied from a blog post.
REQUIRED_KEYWORDS = ["finalizer", "scrapejob-name", "idempotent"]
MIN_KEYWORD_HITS = 2

CP1_TIMEOUT = 180
CP2_TIMEOUT = 180


def check_design_doc():
    sections = check_sections(DESIGN_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    text = DESIGN_PATH.read_text(encoding="utf-8")
    lower = text.lower()
    hits = [kw for kw in REQUIRED_KEYWORDS if kw.lower() in lower]
    if len(hits) < MIN_KEYWORD_HITS:
        not_passed(
            f"DESIGN.md grounds itself in only {len(hits)}/{MIN_KEYWORD_HITS} required concept(s) "
            f"among {REQUIRED_KEYWORDS} (matched: {hits}) -- this needs to be about YOUR operator, not "
            "generic controller-pattern prose"
        )
    return sections, hits


def _run_validator(name, timeout):
    script = TASK_ROOT / "tests" / name
    try:
        return subprocess.run(
            [sys.executable, str(script)],
            cwd=str(TASK_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        not_passed(f"{name} did not exit within {timeout}s (generous safety wrapper -- likely a hang, not slowness)")


@guarded
def main():
    sections, hits = check_design_doc()

    r1 = _run_validator("validate_cp1.py", CP1_TIMEOUT)
    if r1.returncode != 0:
        not_passed(f"CP1 no longer passes -- fix src/ before finishing the design review: {_last_line(r1.stdout or r1.stderr)}")

    r2 = _run_validator("validate_cp2.py", CP2_TIMEOUT)
    if r2.returncode != 0:
        not_passed(f"CP2 no longer passes -- fix src/ before finishing the design review: {_last_line(r2.stdout or r2.stderr)}")

    passed(f"DESIGN.md filled ({len(sections)} sections, grounded concepts: {hits}); CP1 and CP2 both still pass")


if __name__ == "__main__":
    main()
