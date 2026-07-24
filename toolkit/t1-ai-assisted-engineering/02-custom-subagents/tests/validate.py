"""Validator for 02-custom-subagents. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 02-custom-subagents/tests/validate.py

Two gates:
  1. Structural: every .claude/agents/*.md file has valid YAML frontmatter
     with well-formed name/description/tools/model fields; a
     "test-runner" and a "code-reviewer" agent both exist; the
     code-reviewer's body contains a real bulleted checklist.
  2. Doc-gate: WHEN-NOT-TO-DELEGATE.md has its required sections filled in.
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
    read_frontmatter,
)

AGENTS_DIR = TASK_DIR / "deliverable" / ".claude" / "agents"
REQUIRED_AGENT_NAMES = ["test-runner", "code-reviewer"]
MIN_AGENTS = 2
MIN_CHECKLIST_ITEMS = 6

PLACEHOLDER_SUBSTRINGS = ("todo", "fill in")

_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$", re.MULTILINE)

WHEN_NOT_SECTIONS = [
    "When to delegate",
    "When NOT to delegate",
    "Failure modes observed",
]
WHEN_NOT_MIN_CHARS = {
    "When to delegate": 200,
    "When NOT to delegate": 300,
    "Failure modes observed": 200,
    "_default": 150,
}
WHEN_NOT_KEYWORDS = [
    "context",
    "overhead",
    "delegate",
    "tool",
    "subagent",
    "scope",
    "checklist",
]


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SUBSTRINGS)


def _check_str_field(data: dict, key: str, path: Path, required: bool) -> str | None:
    if key not in data:
        if required:
            not_passed(f"{path}: frontmatter missing required field '{key}'")
        return None
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        not_passed(f"{path}: frontmatter field '{key}' must be a non-empty string")
    if _is_placeholder(value):
        not_passed(f"{path}: frontmatter field '{key}' still looks like a placeholder — fill it in")
    return value.strip()


def _check_tools_field(data: dict, path: Path) -> None:
    if "tools" not in data:
        return
    value = data["tools"]
    if isinstance(value, str):
        if _is_placeholder(value):
            not_passed(f"{path}: frontmatter field 'tools' still looks like a placeholder — fill it in")
        names = [t.strip() for t in value.split(",") if t.strip()]
    elif isinstance(value, list):
        names = [str(t).strip() for t in value]
    else:
        not_passed(f"{path}: frontmatter field 'tools' must be a string or list, got {type(value).__name__}")
    if not names:
        not_passed(f"{path}: frontmatter field 'tools' is present but empty")
    bad = [n for n in names if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n)]
    if bad:
        not_passed(f"{path}: frontmatter field 'tools' has malformed tool name(s): {bad}")


def _check_model_field(data: dict, path: Path) -> None:
    if "model" not in data:
        return
    value = data["model"]
    if not isinstance(value, str) or not value.strip():
        not_passed(f"{path}: frontmatter field 'model' must be a non-empty string")
    if _is_placeholder(value):
        not_passed(f"{path}: frontmatter field 'model' still looks like a placeholder — fill it in")


@guarded
def main() -> None:
    if not AGENTS_DIR.is_dir():
        not_passed(f"agents directory not found: {AGENTS_DIR}")

    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    if len(agent_files) < MIN_AGENTS:
        not_passed(f"found {len(agent_files)} agent file(s) under {AGENTS_DIR}, need at least {MIN_AGENTS}")

    by_name: dict[str, tuple[dict, str, Path]] = {}
    for path in agent_files:
        data, body = read_frontmatter(path)
        name = _check_str_field(data, "name", path, required=True)
        _check_str_field(data, "description", path, required=True)
        _check_tools_field(data, path)
        _check_model_field(data, path)
        if not body.strip():
            not_passed(f"{path}: system prompt body is empty")
        if _is_placeholder(body):
            not_passed(f"{path}: system prompt body still looks like a placeholder — fill it in")
        by_name[name] = (data, body, path)

    missing_names = [n for n in REQUIRED_AGENT_NAMES if n not in by_name]
    if missing_names:
        not_passed(
            f"missing required agent(s) by frontmatter 'name': {', '.join(missing_names)} "
            f"(found names: {sorted(by_name)})"
        )

    _, reviewer_body, reviewer_path = by_name["code-reviewer"]
    bullets = [m.group(1) for m in _BULLET_RE.finditer(reviewer_body)]
    bullets = [b for b in bullets if not _is_placeholder(b)]
    if len(bullets) < MIN_CHECKLIST_ITEMS:
        not_passed(
            f"{reviewer_path}: found {len(bullets)}/{MIN_CHECKLIST_ITEMS} non-placeholder "
            "checklist bullet item(s) in the code-reviewer system prompt"
        )

    when_not_path = TASK_DIR / "deliverable" / "WHEN-NOT-TO-DELEGATE.md"
    check_sections(when_not_path, WHEN_NOT_SECTIONS, WHEN_NOT_MIN_CHARS)
    full_text = read_doc(when_not_path)
    check_keywords(full_text, WHEN_NOT_KEYWORDS, min_hits=4, label="WHEN-NOT-TO-DELEGATE.md grounding vocabulary")

    passed(f"{len(agent_files)} agent(s) validated, code-reviewer checklist has {len(bullets)} items")


if __name__ == "__main__":
    main()
