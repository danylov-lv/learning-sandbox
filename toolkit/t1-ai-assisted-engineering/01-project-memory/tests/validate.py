"""Validator for 01-project-memory. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 01-project-memory/tests/validate.py

Purely structural (doc-gate): required `##` sections exist and meet a
minimum length, no leftover `[fill in ...]` placeholders, enough grounding
vocabulary specific to the given sample-project appears, and the exact
test command for sample-project is actually named somewhere in the file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_keywords,
    check_sections,
    guarded,
    not_passed,
    passed,
    read_doc,
)

REQUIRED_SECTIONS = [
    "Commands",
    "Conventions",
    "Architecture",
    "What NOT to do",
    "Memory vs rot",
]

MIN_CHARS = {
    "Commands": 120,
    "Conventions": 250,
    "Architecture": 200,
    "What NOT to do": 200,
    "Memory vs rot": 300,
    "_default": 150,
}

GROUNDING_KEYWORDS = [
    "pytest",
    "cents",
    "float",
    "parse_price",
    "format_price",
    "currency",
    "priceparser",
    "none",
    "iso",
    "rounding",
]

ROT_KEYWORDS = [
    "rot",
    "stale",
    "volatile",
    "secret",
    "transient",
    "outdated",
    "drift",
]

TEST_COMMAND_RE = re.compile(r"pytest\s+tests\b", re.IGNORECASE)


@guarded
def main() -> None:
    deliverable_path = TASK_DIR / "deliverable" / "CLAUDE.md"
    sections = check_sections(deliverable_path, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = read_doc(deliverable_path)
    check_keywords(
        full_text,
        GROUNDING_KEYWORDS,
        min_hits=6,
        label="CLAUDE.md grounding vocabulary (specific to sample-project)",
    )

    if not TEST_COMMAND_RE.search(full_text):
        not_passed(
            "the 'Commands' section must name sample-project's real test invocation "
            "(something matching 'pytest tests', e.g. 'uv run pytest tests -q' from "
            "sample-project/) — this wasn't found anywhere in the file"
        )

    check_keywords(
        sections["Memory vs rot"],
        ROT_KEYWORDS,
        min_hits=2,
        label="'Memory vs rot' section — reflection vocabulary",
    )

    passed("CLAUDE.md structure, grounding, and test-command reference OK")


if __name__ == "__main__":
    main()
