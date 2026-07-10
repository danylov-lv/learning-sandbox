"""Validator for 09-rmq-vs-kafka-writeup.

Run from this task's directory:
    uv run python tests/validate.py

This is a written task — no infrastructure required. The validator checks that
ANSWER.md and NOTES.md are substantively filled in with the learner's own analysis.
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
    "## The current RMQ pipeline",
    "## Where Kafka would help",
    "## Where Kafka would NOT help / would be overkill",
    "## The partition-count / ordering tradeoff",
    "## Migration verdict",
]

# Required keywords (case-insensitive); at least one variant per concept must appear
REQUIRED_KEYWORDS = {
    "replay": ["replay"],
    "compaction": ["compaction"],
    "consumer_group": ["consumer group"],
    "offset": ["offset"],
    "exactly_once": ["exactly-once", "idempotent"],
    "lag_backpressure": ["backpressure", "lag"],
    "partition": ["partition"],
    "retention": ["retention"],
}

MIN_SECTION_CONTENT = 200  # minimum chars of actual content per section (beyond the shipped prompt)
MIN_NOTES_CONTENT = 300    # minimum chars of actual content in NOTES.md


def extract_section_content(text, heading):
    """Extract content under a heading until the next heading or EOF.

    Returns the raw content string (everything after the heading line).
    """
    # Find the heading line
    pattern = re.escape(heading) + r"\n"
    match = re.search(pattern, text)
    if not match:
        return None

    start = match.end()

    # Find the next heading (starts with ## at line start)
    next_heading = re.search(r"\n##", text[start:])
    if next_heading:
        end = start + next_heading.start()
    else:
        end = len(text)

    return text[start:end].strip()


def count_content_chars(section_text):
    """Count meaningful content chars in a section (exclude empty lines, leading prompts)."""
    if not section_text:
        return 0

    # Split into lines and filter out mostly-empty lines
    lines = section_text.split("\n")
    content = [line.strip() for line in lines if line.strip()]

    # Join and return length (this counts all non-whitespace content)
    return len("\n".join(content))


def check_headings(text):
    """Check that all required headings are present."""
    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing:
        return False, f"missing required section heading(s): {missing}"
    return True, ""


def check_section_content(text):
    """Check that each section has substantial content."""
    issues = []
    for heading in REQUIRED_HEADINGS:
        content = extract_section_content(text, heading)
        if content is None:
            issues.append(f"could not find content for '{heading}'")
            continue

        char_count = count_content_chars(content)
        if char_count < MIN_SECTION_CONTENT:
            heading_name = heading.replace("## ", "")
            issues.append(
                f"section '{heading_name}' has only {char_count} chars of content, "
                f"expected at least {MIN_SECTION_CONTENT} (looks unfilled)"
            )

    if issues:
        return False, "; ".join(issues)
    return True, ""


def check_keywords(text):
    """Check that required keywords are present (case-insensitive)."""
    text_lower = text.lower()
    missing = []

    for concept, variants in REQUIRED_KEYWORDS.items():
        found = any(variant.lower() in text_lower for variant in variants)
        if not found:
            missing.append(concept.replace("_", " "))

    if missing:
        return False, f"document missing required concept keywords: {missing}"
    return True, ""


def check_notes(text):
    """Check that NOTES.md is substantively filled."""
    # Remove the template headers to count actual content
    content = text
    for header in ["## What I learned", "## Gotchas", "## Open questions"]:
        content = content.replace(header, "")

    content = content.strip()
    char_count = len(content)

    if char_count < MIN_NOTES_CONTENT:
        return False, (
            f"NOTES.md has only {char_count} chars of content, expected at least {MIN_NOTES_CONTENT} "
            "(looks like the template was left mostly unfilled)"
        )
    return True, ""


@guarded
def main():
    # Check ANSWER.md exists
    if not ANSWER_PATH.exists():
        not_passed(f"missing {ANSWER_PATH}")

    answer_text = ANSWER_PATH.read_text(encoding="utf-8")

    # Check required headings
    ok, msg = check_headings(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    # Check section content
    ok, msg = check_section_content(answer_text)
    if not ok:
        not_passed(f"ANSWER.md: {msg}")

    # Check required keywords
    ok, msg = check_keywords(answer_text)
    if not ok:
        not_passed(msg)

    # Check NOTES.md exists
    if not NOTES_PATH.exists():
        not_passed(f"missing {NOTES_PATH}")

    notes_text = NOTES_PATH.read_text(encoding="utf-8")

    # Check NOTES.md content
    ok, msg = check_notes(notes_text)
    if not ok:
        not_passed(msg)

    passed("ANSWER.md has all required sections filled with substance; NOTES.md completed")


if __name__ == "__main__":
    main()
