"""Validator for 20-kubernetes task 06 (reverse-engineer-company-template).

Run from this task directory:

    uv run python tests/validate.py

No cluster required. Two gates:

Gate 1 (fixture sanity): `helm lint` and `helm template` on
given/company-chart must succeed, both with defaults and with
values-example.yaml -- this protects the fixture chart itself, not
anything the learner wrote.

Gate 2 (doc gate): structural checks on ANALYSIS.md -- the four required
sections exist and are substantial, questions.md's Q1-Q6 are each
answered with original content (not a restated question), and the
"Questionable decisions" section demonstrates the learner actually found
at least two of the three planted smells in given/company-chart (judged
by grounding keywords, not exact wording).
"""

from __future__ import annotations

import subprocess
import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    passed,
    not_passed,
    check_sections,
    check_answers,
)

CHART_DIR = TASK_DIR / "given" / "company-chart"
ANALYSIS_PATH = TASK_DIR / "ANALYSIS.md"
QUESTIONS_PATH = TASK_DIR / "questions.md"

REQUIRED_SECTIONS = [
    "How the template is organized",
    "Every decision explained",
    "Questionable decisions",
    "What I would ask the platform team",
]

MIN_CHARS = {
    "How the template is organized": 400,
    "Every decision explained": 1200,
    "Questionable decisions": 600,
    "What I would ask the platform team": 300,
    "_default": 300,
}

# Each inner list is an AND-group: every pattern in it must be found
# (case-insensitive substring or regex) for that plant to count as
# identified. At least 2 of these 3 groups must be satisfied somewhere in
# the "Questionable decisions" section for the learner to pass -- this
# module plants exactly 3 smells in given/company-chart (see
# .authoring/notes-t06.md for the answer key; never shown to the learner).
PLANT_GROUPS = [
    ("imagePullPolicy: Always + floating latest tag",
     [r"pull\s*policy", r"always", r"latest"]),
    ("liveness probe checks dependencies -> restart storms",
     [r"liveness", r"cascad|restart storm|dependenc"]),
    ("shared secret + no checksum annotation -> silent drift",
     [r"checksum", r"secret|rotat|roll"]),
]


def _run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        not_passed(f"'{cmd[0]}' not found on PATH -- helm must be installed")
    except subprocess.TimeoutExpired:
        not_passed(f"{' '.join(cmd)} timed out")


def _check_fixture_renders() -> None:
    if not CHART_DIR.exists():
        not_passed(f"fixture chart not found: {CHART_DIR}")

    result = _run(["helm", "lint", "."], cwd=CHART_DIR)
    if result.returncode != 0:
        not_passed(f"helm lint given/company-chart failed: {result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr.strip()}")

    result = _run(["helm", "template", "fixture-check", "."], cwd=CHART_DIR)
    if result.returncode != 0:
        not_passed(f"helm template given/company-chart (defaults) failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")
    default_rendered = result.stdout
    for kind in ("kind: Deployment", "kind: Service", "kind: ConfigMap", "kind: Secret"):
        if kind not in default_rendered:
            not_passed(f"helm template (defaults) did not render any {kind} -- fixture chart is broken")

    result = _run(["helm", "template", "fixture-check", ".", "-f", "values-example.yaml"], cwd=CHART_DIR)
    if result.returncode != 0:
        not_passed(f"helm template given/company-chart (values-example.yaml) failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")
    example_rendered = result.stdout

    for name in ("api", "worker"):
        if f"-{name}\n" not in example_rendered and f"-{name}-" not in example_rendered and f" {name}\n" not in example_rendered:
            # Loose check only -- the strict per-component structural check
            # below via default_rendered's Deployment count is the real gate.
            pass

    dep_count = default_rendered.count("kind: Deployment")
    if dep_count < 2:
        not_passed(f"expected at least 2 Deployments rendered (api + worker components), found {dep_count}")


@guarded
def main() -> None:
    _check_fixture_renders()

    sections = check_sections(ANALYSIS_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = ANALYSIS_PATH.read_text(encoding="utf-8")
    if "[fill in" in full_text:
        not_passed("ANALYSIS.md still contains an unfilled '[fill in' marker")

    questionable = sections["Questionable decisions"]
    lowered = questionable.lower()
    satisfied = []
    for label, patterns in PLANT_GROUPS:
        if all(re.search(p, lowered) for p in patterns):
            satisfied.append(label)
    if len(satisfied) < 2:
        not_passed(
            "'Questionable decisions' section must identify at least 2 of the 3 planted "
            f"issues in given/company-chart (grounding-keyword match); only matched: {satisfied or '(none)'}"
        )

    check_answers(
        ANALYSIS_PATH,
        [f"Q{i}" for i in range(1, 7)],
        min_answered=6,
        min_chars=300,
        questions_path=QUESTIONS_PATH,
        min_original_chars=300,
    )

    passed(
        f"fixture chart lints/renders cleanly; ANALYSIS.md structurally complete; "
        f"{len(satisfied)}/3 planted issues identified; all 6 hostile-review questions answered"
    )


if __name__ == "__main__":
    main()
