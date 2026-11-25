"""CP2 -- architecture/failure-mode design-doc sections, plus the three
Architecture Decision Records.

Two checks, in order:

1. `DESIGN.md` has the eight CP2 sections, each long enough, each
   mentioning grounding keywords, each making quantitative claims, none
   still containing a placeholder marker.
2. `docs/adr-001.md`, `docs/adr-002.md`, `docs/adr-003.md` each follow the
   fixed template (`## Context`, `## Decision`, `## Alternatives
   considered`, `## Consequences`), clear a minimum length, contain no
   placeholder markers, and list at least two bulleted rejected
   alternatives under `## Alternatives considered`.

Any failure is `NOT PASSED`, naming which check failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    check_keywords,
    check_no_placeholders,
    check_quantitative,
    check_sections,
    guarded,
    not_passed,
    passed,
    read_doc,
)

DESIGN_PATH = TASK_ROOT / "DESIGN.md"
DOCS_DIR = TASK_ROOT / "docs"

REQUIRED_SECTIONS = [
    "Architecture",
    "Component responsibilities",
    "Data flow and contracts",
    "Storage and serving layout",
    "Multi-tenancy and isolation",
    "Failure modes and blast radius",
    "Degradation ladder",
    "Evolution at 10x",
]

_MIN_CHARS = 250

_GROUNDING_KEYWORDS = [
    "shard", "replica", "partition", "backpressure", "circuit breaker",
    "queue", "quota", "blast radius", "shed", "degrade", "isolation",
    "tenant", "index", "schema", "contract", "idempotent", "retry",
    "failover",
]
_MIN_KEYWORD_HITS = 6
_MIN_NUMERIC_TOKENS = 6

ADR_FILES = ["adr-001.md", "adr-002.md", "adr-003.md"]
ADR_REQUIRED_SECTIONS = ["Context", "Decision", "Alternatives considered", "Consequences"]
_ADR_MIN_CHARS = {
    "Context": 120,
    "Decision": 80,
    "Alternatives considered": 150,
    "Consequences": 100,
}
_ADR_MIN_BULLETS = 2


def _count_bullets(body: str) -> int:
    count = 0
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            count += 1
    return count


def _check_adr(path: Path) -> None:
    if not path.exists():
        not_passed(f"{path.name} is missing")
    sections = check_sections(path, ADR_REQUIRED_SECTIONS, _ADR_MIN_CHARS)

    alt_body = sections["Alternatives considered"]
    bullets = _count_bullets(alt_body)
    if bullets < _ADR_MIN_BULLETS:
        not_passed(
            f"{path.name}: '## Alternatives considered' lists {bullets} bulleted "
            f"alternative(s), need at least {_ADR_MIN_BULLETS} -- argue the rejected "
            f"alternatives fairly, do not just name-drop them"
        )

    full_text = read_doc(path)
    check_no_placeholders(full_text, path.name)


def _check_adrs() -> None:
    for name in ADR_FILES:
        _check_adr(DOCS_DIR / name)


def _check_design_doc() -> None:
    sections = check_sections(DESIGN_PATH, REQUIRED_SECTIONS, _MIN_CHARS)
    body_for_keywords = "\n".join(sections[h] for h in REQUIRED_SECTIONS)

    check_keywords(body_for_keywords, _GROUNDING_KEYWORDS, _MIN_KEYWORD_HITS, "DESIGN.md (CP2 sections)")

    quant_body = "\n".join(
        sections[h] for h in ("Storage and serving layout", "Degradation ladder", "Evolution at 10x")
    )
    check_quantitative(quant_body, _MIN_NUMERIC_TOKENS, "DESIGN.md (Storage layout / Degradation ladder / Evolution at 10x)")


@guarded
def main() -> None:
    _check_design_doc()
    _check_adrs()
    passed("CP2: DESIGN.md architecture/failure sections filled in, and all three ADRs are well-formed")


if __name__ == "__main__":
    main()
