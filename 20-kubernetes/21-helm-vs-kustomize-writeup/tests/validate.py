"""Validator for 20-kubernetes task 21 (helm-vs-kustomize-writeup).

Run from this task directory:

    uv run python tests/validate.py

No cluster required, no kubectl/kind calls at all -- this is a pure
written-comparison task. Two gates:

Gate 1 (doc gate): structural checks on COMPARISON.md -- the four
required sections exist and are substantial, with no leftover
'[fill in' markers.

Gate 2 (grounding + hostile review): the document uses enough of the
module's Helm/Kustomize vocabulary to rule out vocabulary-free
hand-waving, and questions.md's Q1-Q5 are each answered under
'## Hostile review' with original content (not a restated question).
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness import common  # noqa: E402

COMPARISON_PATH = TASK_ROOT / "COMPARISON.md"
QUESTIONS_PATH = TASK_ROOT / "questions.md"

REQUIRED_SECTIONS = [
    "Mental models",
    "Where Helm wins",
    "Where Kustomize wins",
    "Decision",
]

MIN_CHARS = {
    "Mental models": 500,
    "Where Helm wins": 400,
    "Where Kustomize wins": 400,
    "Decision": 400,
    "_default": 300,
}

# Grounding vocabulary -- a passing writeup must actually engage with the
# module's Helm/Kustomize terminology, not just assert an opinion.
GROUNDING_KEYWORDS = [
    "values.yaml",
    "overlay",
    "patch",
    "kustomization",
    "base",
    "subchart",
    "dependencies",
    "hook",
    "checksum",
    "argo cd",
    "app-of-apps",
    "strategic merge",
    "json 6902",
    "secretgenerator",
    "configmapgenerator",
    "component",
    "template",
    "chart.yaml",
]
MIN_GROUNDING_HITS = 8

QUESTION_IDS = [f"Q{i}" for i in range(1, 6)]


@common.guarded
def main() -> None:
    sections = common.check_sections(COMPARISON_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = COMPARISON_PATH.read_text(encoding="utf-8")
    if "[fill in" in full_text:
        common.not_passed("COMPARISON.md still contains an unfilled '[fill in' marker")

    common.check_keywords(
        full_text,
        GROUNDING_KEYWORDS,
        MIN_GROUNDING_HITS,
        "COMPARISON.md",
    )

    common.check_answers(
        COMPARISON_PATH,
        QUESTION_IDS,
        min_answered=5,
        min_chars=250,
        questions_path=QUESTIONS_PATH,
        min_original_chars=150,
    )

    common.passed(
        f"COMPARISON.md structurally complete ({len(sections)} required sections); "
        f"grounding vocabulary present; all 5 hostile-review questions answered"
    )


if __name__ == "__main__":
    main()
