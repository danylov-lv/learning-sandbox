"""Validator for 05-history-design-writeup. Run from the task directory:

    uv run python tests/validate.py

Doc-gate only (no service, no capacity model): required `##` sections
exist and meet a minimum length, no leftover `[fill in ...]` placeholder
markers, grounding keywords appear, quantitative-or-concrete claims are
present, and the Q1..Q6 hostile-review subsections are genuinely
answered (not missing, not a placeholder, not a verbatim copy of the
question, not too short).
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_answers,
    check_keywords,
    check_quantitative,
    check_sections,
    guarded,
    passed,
    read_doc,
)

REQUIRED_SECTIONS = [
    "Commit granularity and atomicity",
    "Commit message convention",
    "Merge strategy: rebase vs merge vs squash",
    "Handling mistakes: amend, revert, and rewriting shared history",
    "Bisectability and blame hygiene",
    "Hostile review responses",
]

MIN_CHARS = {
    "Commit granularity and atomicity": 300,
    "Commit message convention": 300,
    "Merge strategy: rebase vs merge vs squash": 300,
    "Handling mistakes: amend, revert, and rewriting shared history": 300,
    "Bisectability and blame hygiene": 250,
    "Hostile review responses": 1100,
    "_default": 200,
}

KEYWORDS = [
    "atomic",
    "atomicity",
    "bisect",
    "bisectable",
    "bisectability",
    "revert",
    "amend",
    "squash",
    "squash-merge",
    "rebase",
    "merge commit",
    "fast-forward",
    "conventional commit",
    "conventional-commit",
    "fixup",
    "force-push",
    "force push",
    "branch protection",
    "blame",
    "cherry-pick",
    "imperative",
    "subject line",
    "wip",
    "linear history",
    "shared history",
]

QUESTION_IDS = [f"Q{i}" for i in range(1, 7)]


@guarded
def main() -> None:
    policy_path = TASK_DIR / "POLICY.md"
    check_sections(policy_path, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = read_doc(policy_path)
    check_keywords(full_text, KEYWORDS, min_hits=9, label="POLICY.md grounding vocabulary")
    check_quantitative(full_text, min_numbers=6, label="POLICY.md")

    check_answers(
        policy_path,
        QUESTION_IDS,
        min_answered=6,
        min_chars=200,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )

    passed("POLICY.md structure, grounding vocabulary, and all 6 hostile-review answers OK")


if __name__ == "__main__":
    main()
