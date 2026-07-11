"""Validator for 08-when-clickhouse-when-duckdb.

Run from this task's directory:
    uv run python tests/validate.py

This is a written task -- no live stack required. The validator checks that
ANSWER.md and NOTES.md are substantively filled in with the learner's own
analysis, not left as the shipped template.
"""

import re
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

ANSWER_PATH = TASK_ROOT / "ANSWER.md"
NOTES_PATH = TASK_ROOT / "NOTES.md"

# Required section headings (exact match, case-sensitive)
REQUIRED_HEADINGS = [
    "## Where ClickHouse (server) earns its keep",
    "## Where DuckDB (embedded) is the right call",
    "## Where neither — keep it in Postgres",
    "## Three concrete calls",
    "## What surprised me",
]

THREE_CALLS_HEADING = "## Three concrete calls"

# At least two of these concepts must show up in "Three concrete calls" --
# proof the decisions are grounded in what was actually built/measured,
# not asserted from first principles.
GROUNDING_KEYWORDS = {
    "materialized_view": ["materialized view"],
    "ttl": ["ttl"],
    "replacingmergetree": ["replacingmergetree"],
    "partition_pruning": ["partition", "pruning", "prune"],
    "ratio_benchmark": ["ratio", "benchmark"],
}
MIN_GROUNDING_HITS = 2

PLACEHOLDER_MARKER = "(fill in"

MIN_SECTION_CONTENT = 250  # minimum chars of actual content per section
MIN_NOTES_CONTENT = 200    # minimum chars of actual content in NOTES.md


def extract_section_content(text, heading):
    """Extract content under a heading until the next heading or EOF."""
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
    """Return (ok, message, per_section_counts). Fails on placeholder text
    still present, or on content below the minimum length."""
    issues = []
    counts = {}
    for heading in REQUIRED_HEADINGS:
        content = extract_section_content(text, heading)
        name = heading.replace("## ", "")
        if content is None:
            issues.append(f"could not find content for '{name}'")
            counts[name] = 0
            continue

        if PLACEHOLDER_MARKER in content:
            issues.append(f"section '{name}' still contains the shipped '(fill in' placeholder")

        char_count = count_content_chars(content)
        counts[name] = char_count
        if char_count < MIN_SECTION_CONTENT:
            issues.append(
                f"section '{name}' has only {char_count} chars of content, "
                f"expected at least {MIN_SECTION_CONTENT} (looks unfilled)"
            )

    if issues:
        return False, "; ".join(issues), counts
    return True, "", counts


def check_grounding(text):
    """The 'Three concrete calls' section must reference at least
    MIN_GROUNDING_HITS distinct concepts from the module, so the decisions
    are tied to what was actually built/measured."""
    content = extract_section_content(text, THREE_CALLS_HEADING)
    if content is None:
        return False, f"could not find content for '{THREE_CALLS_HEADING}'"

    content_lower = content.lower()
    hits = []
    for concept, variants in GROUNDING_KEYWORDS.items():
        if any(v in content_lower for v in variants):
            hits.append(concept)

    if len(hits) < MIN_GROUNDING_HITS:
        return False, (
            f"'Three concrete calls' only references {len(hits)} module concept(s) "
            f"({hits}), expected at least {MIN_GROUNDING_HITS} of: "
            f"materialized view, TTL, ReplacingMergeTree, partition/pruning, ratio/benchmark"
        )
    return True, ""


def check_notes(text):
    content = text
    for header in ["## What I learned", "## Gotchas", "## Open questions"]:
        content = content.replace(header, "")
    content = content.strip()
    char_count = len(content)

    if char_count < MIN_NOTES_CONTENT:
        return False, (
            f"NOTES.md has only {char_count} chars of content, expected at least "
            f"{MIN_NOTES_CONTENT} (looks like the template was left mostly unfilled)"
        )
    return True, ""


@guarded
def main():
    if not ANSWER_PATH.exists():
        not_passed(f"missing {ANSWER_PATH}")

    answer_text = ANSWER_PATH.read_text(encoding="utf-8")

    ok, msg = check_headings(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    ok, msg, counts = check_sections(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    ok, msg = check_grounding(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    if not NOTES_PATH.exists():
        not_passed(f"missing {NOTES_PATH}")

    notes_text = NOTES_PATH.read_text(encoding="utf-8")
    ok, msg = check_notes(notes_text)
    if not ok:
        not_passed(msg)

    summary = ", ".join(f"{name}={n} chars" for name, n in counts.items())
    passed(f"ANSWER.md filled ({summary}); NOTES.md completed")


if __name__ == "__main__":
    main()
