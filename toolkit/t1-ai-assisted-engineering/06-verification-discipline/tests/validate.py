"""Validator for 06-verification-discipline. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 06-verification-discipline/tests/validate.py

Two independent gates, both must pass:
  1. REVIEW.md: each patch's `### patchNN` subsection is genuinely
     answered (doc-gate: present, long enough, not a placeholder, not
     copied from the patch's own PR description) AND its "Verdict:"
     value matches this validator's own ground truth (BUGGY/CLEAN) --
     never read from .authoring at runtime; the ground truth lives here.
  2. tests_learner/test_patchNN.py, run individually as a real pytest
     subprocess against the SHIPPED code in patches/patchNN/code.py
     (never a hidden "fixed" variant -- there isn't one; see
     .authoring/design.md for why that's enough): must FAIL for every
     BUGGY patch and PASS for the CLEAN control. A test that trivially
     always fails or always passes is caught by requiring both
     directions to hold across the 4 patches, plus a structural check
     that each test file actually imports the matching patch module.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_answers,
    guarded,
    not_passed,
    parse_subsections,
    passed,
    read_doc,
    run_pytest,
)

# Ground truth. Not read from .authoring/ at runtime -- this validator IS
# the objective source of truth; .authoring/design.md documents the same
# facts for a human reading the spoilers file after finishing the task.
GROUND_TRUTH = {
    "patch01": "BUGGY",
    "patch02": "BUGGY",
    "patch03": "BUGGY",
    "patch04": "CLEAN",
}

REVIEW_PATH = TASK_DIR / "REVIEW.md"
PR_DESCRIPTIONS_PATH = TASK_DIR / "tests" / "pr-descriptions-combined.md"
TESTS_LEARNER_DIR = TASK_DIR / "tests_learner"

_VERDICT_RE = re.compile(r"^\s*Verdict:\s*(BUGGY|CLEAN)\s*$", re.MULTILINE | re.IGNORECASE)

PYTEST_TIMEOUT = 60


def _check_verdicts() -> dict:
    patch_ids = list(GROUND_TRUTH)

    # Doc-gate: presence, length, not placeholder, not copied from the
    # patch's own PR description.
    check_answers(
        REVIEW_PATH,
        patch_ids,
        min_answered=len(patch_ids),
        min_chars=120,
        questions_path=PR_DESCRIPTIONS_PATH,
        min_original_chars=80,
    )

    text = read_doc(REVIEW_PATH)
    subsections = parse_subsections(text)

    mismatches = []
    for pid in patch_ids:
        body = subsections.get(pid, "")
        m = _VERDICT_RE.search(body)
        if not m:
            not_passed(f"REVIEW.md: '### {pid}' has no parseable 'Verdict: BUGGY' or 'Verdict: CLEAN' line")
        verdict = m.group(1).upper()
        if verdict != GROUND_TRUTH[pid]:
            mismatches.append(pid)

    if mismatches:
        not_passed(f"REVIEW.md verdict(s) incorrect for: {', '.join(mismatches)}")

    return subsections


def _check_learner_test(pid: str) -> None:
    test_path = TESTS_LEARNER_DIR / f"test_{pid}.py"
    if not test_path.exists():
        not_passed(f"missing {test_path}")

    text = read_doc(test_path)
    if pid not in text:
        not_passed(f"{test_path}: doesn't reference '{pid}' anywhere (must import from patches.{pid}.code)")

    rel_path = str(test_path.relative_to(TASK_DIR)).replace("\\", "/")
    result = run_pytest([rel_path], cwd=TASK_DIR, timeout=PYTEST_TIMEOUT)

    if result.timed_out:
        not_passed(f"{test_path}: timed out after {PYTEST_TIMEOUT}s")
    if result.collected < 1:
        not_passed(f"{test_path}: pytest collected 0 tests — write at least one real test function")

    expected_verdict = GROUND_TRUTH[pid]
    if expected_verdict == "BUGGY":
        if result.passed:
            not_passed(
                f"{test_path}: PASSED against the shipped (buggy) patches/{pid}/code.py — "
                f"it must FAIL to genuinely catch the planted bug.\n{result.output_tail}"
            )
    else:
        if not result.passed:
            not_passed(
                f"{test_path}: FAILED against the shipped (clean) patches/{pid}/code.py — "
                f"the clean control must PASS.\n{result.output_tail}"
            )


@guarded
def main() -> None:
    _check_verdicts()

    for pid in GROUND_TRUTH:
        _check_learner_test(pid)

    passed(f"REVIEW.md verdicts correct and all {len(GROUND_TRUTH)} learner tests behave as required")


if __name__ == "__main__":
    main()
