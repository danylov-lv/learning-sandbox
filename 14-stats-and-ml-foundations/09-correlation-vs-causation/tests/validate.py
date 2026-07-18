"""Validator for 14-stats-and-ml-foundations task 09 -- correlation-vs-causation.

Two independent things must be true, checked in this order:

1. The analysis functions in `src/confounding.py` produce numbers that
   match an independently recomputed reference (this validator computes
   `pooled_correlation` and `within_category_correlations` itself, straight
   from `load_observations()`, using the same two columns the learner's
   functions see -- there is no hidden ground-truth file for this task,
   Pearson correlation is cheap and exact to recompute), the within-category
   correlations are all small (nowhere near the pooled value -- the
   signature of a confound collapsing under stratification), and
   `identify_confounder` names `category`. `make_figure` is checked
   structurally (a real Figure with drawn content).
2. `ANSWER.md` is filled in with the learner's own reasoning about why the
   pooled correlation is spurious, grounded in the numbers above -- not
   left as the shipped template.

Run from this task's directory:

    uv run python tests/validate.py
"""

import re
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import check_close, guarded, load_observations, not_passed, passed, require_figure  # noqa: E402
from src.confounding import (  # noqa: E402
    identify_confounder,
    make_figure,
    pooled_correlation,
    within_category_correlations,
)

ANSWER_PATH = TASK_ROOT / "ANSWER.md"

# --------------------------------------------------------------------------
# Thresholds -- see .authoring/design.md for the measured reference values
# (pooled r ~= 0.794, within-category r ranges ~0.006-0.063). Margins here
# are wide enough to not be flaky while still being unmistakably diagnostic
# of "did the confound actually collapse under stratification."
# --------------------------------------------------------------------------

CORR_REL_TOL = 1e-3
CORR_ABS_TOL = 1e-3

MAX_WITHIN_ABS_R = 0.2       # every within-category |r| must stay well under this
MIN_POOLED_VS_WITHIN_GAP = 0.4  # pooled r must exceed the largest within-category |r| by at least this much

REQUIRED_HEADINGS = [
    "## The naive conclusion",
    "## What the within-category analysis shows",
    "## The confounder",
    "## Correlation vs causation",
    "## What evidence would support a causal claim",
]

GROUNDING_KEYWORDS = {
    "confounder": ["confound"],
    "category": ["category"],
    "spurious": ["spurious"],
    "simpson": ["simpson"],
    "causation": ["causation", "causal"],
    "within-category": ["within-category", "within category", "stratif"],
}
MIN_GROUNDING_HITS = 4

PLACEHOLDER_MARKER = "[fill in"
MIN_SECTION_CONTENT = 120  # minimum chars of actual content per section


# --------------------------------------------------------------------------
# Reference computation -- independent of src/confounding.py, straight from
# the dataset.
# --------------------------------------------------------------------------

def reference_pooled_correlation(df):
    return float(df["discount_pct"].corr(df["units_sold"]))


def reference_within_category_correlations(df):
    out = {}
    for cat, sub in df.groupby("category"):
        out[cat] = float(sub["discount_pct"].corr(sub["units_sold"]))
    return out


# --------------------------------------------------------------------------
# ANSWER.md writeup gating (same pattern as module 11 task 06)
# --------------------------------------------------------------------------

def extract_section_content(text, heading):
    pattern = re.escape(heading) + r"\n"
    match = re.search(pattern, text)
    if not match:
        return None
    start = match.end()
    next_heading = re.search(r"\n##", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def count_content_chars(section_text):
    if not section_text:
        return 0
    lines = section_text.split("\n")
    content = [line.strip() for line in lines if line.strip()]
    return len("\n".join(content))


def check_headings(text):
    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing:
        return False, f"missing required section heading(s): {missing}"
    return True, ""


def check_sections(text):
    issues = []
    for heading in REQUIRED_HEADINGS:
        content = extract_section_content(text, heading)
        name = heading.replace("## ", "")
        if content is None:
            issues.append(f"could not find content for '{name}'")
            continue

        if PLACEHOLDER_MARKER in content:
            issues.append(f"section '{name}' still contains the shipped '[fill in' placeholder")

        char_count = count_content_chars(content)
        if char_count < MIN_SECTION_CONTENT:
            issues.append(
                f"section '{name}' has only {char_count} chars of content, "
                f"expected at least {MIN_SECTION_CONTENT} (looks unfilled)"
            )

    if issues:
        return False, "; ".join(issues)
    return True, ""


def check_grounding(text):
    text_lower = text.lower()
    hits = []
    for concept, variants in GROUNDING_KEYWORDS.items():
        if any(v in text_lower for v in variants):
            hits.append(concept)

    if len(hits) < MIN_GROUNDING_HITS:
        missing = sorted(set(GROUNDING_KEYWORDS) - set(hits))
        return False, (
            f"ANSWER.md only references {len(hits)} module concept(s) "
            f"({sorted(hits)}), expected at least {MIN_GROUNDING_HITS} of "
            f"{sorted(GROUNDING_KEYWORDS)} (missing: {missing})"
        )
    return True, ""


@guarded
def main():
    df = load_observations()

    ref_pooled = reference_pooled_correlation(df)
    ref_within = reference_within_category_correlations(df)

    # --- pooled_correlation --------------------------------------------
    got_pooled = pooled_correlation(df)
    if not isinstance(got_pooled, (int, float)):
        not_passed(f"pooled_correlation must return a float, got {type(got_pooled).__name__}")
    ok, msg = check_close("pooled_correlation", float(got_pooled), ref_pooled, rel=CORR_REL_TOL, abs_=CORR_ABS_TOL)
    if not ok:
        not_passed(msg)

    # --- within_category_correlations -----------------------------------
    got_within = within_category_correlations(df)
    if not isinstance(got_within, dict):
        not_passed(f"within_category_correlations must return a dict, got {type(got_within).__name__}")

    missing_cats = set(ref_within) - set(got_within)
    if missing_cats:
        not_passed(f"within_category_correlations is missing categorie(s): {sorted(missing_cats)}")
    extra_cats = set(got_within) - set(ref_within)
    if extra_cats:
        not_passed(f"within_category_correlations has unexpected categorie(s) not in the dataset: {sorted(extra_cats)}")

    for cat, ref_r in ref_within.items():
        got_r = got_within[cat]
        if not isinstance(got_r, (int, float)):
            not_passed(f"within_category_correlations[{cat!r}] is not a float: {got_r!r}")
        ok, msg = check_close(
            f"within_category_correlations[{cat!r}]", float(got_r), ref_r, rel=CORR_REL_TOL, abs_=CORR_ABS_TOL
        )
        if not ok:
            not_passed(msg)

    max_within_abs_r = max(abs(r) for r in ref_within.values())
    if max_within_abs_r > MAX_WITHIN_ABS_R:
        not_passed(
            f"reference within-category |r| reached {max_within_abs_r:.4f}, above the "
            f"{MAX_WITHIN_ABS_R} sanity ceiling -- dataset/reference mismatch, not a learner error"
        )
    if ref_pooled - max_within_abs_r < MIN_POOLED_VS_WITHIN_GAP:
        not_passed(
            f"reference pooled r ({ref_pooled:.4f}) minus max within-category |r| "
            f"({max_within_abs_r:.4f}) is below the {MIN_POOLED_VS_WITHIN_GAP} gap this "
            f"task expects to demonstrate -- dataset/reference mismatch, not a learner error"
        )

    # --- identify_confounder ---------------------------------------------
    got_confounder = identify_confounder(df)
    if got_confounder != "category":
        not_passed(
            f"identify_confounder(df) returned {got_confounder!r}, expected 'category' -- "
            f"compare pooled_correlation against within_category_correlations: stratifying "
            f"by category is what makes the pooled association collapse"
        )

    # --- make_figure -------------------------------------------------------
    fig = make_figure(df)
    ok, msg = require_figure(fig, min_axes=1)
    if not ok:
        not_passed(msg)

    # --- ANSWER.md writeup gating ------------------------------------------
    if not ANSWER_PATH.exists():
        not_passed(f"missing {ANSWER_PATH}")

    answer_text = ANSWER_PATH.read_text(encoding="utf-8")

    ok, msg = check_headings(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    ok, msg = check_sections(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    ok, msg = check_grounding(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    passed(
        f"pooled r={ref_pooled:.3f}, max within-category |r|={max_within_abs_r:.3f}, "
        f"confounder='category'; ANSWER.md filled"
    )


if __name__ == "__main__":
    main()
