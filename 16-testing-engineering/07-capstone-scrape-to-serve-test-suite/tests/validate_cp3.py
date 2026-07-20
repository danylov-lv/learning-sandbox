"""CP3 -- the test-strategy memo, plus a green re-run of CP1 and CP2.

Two checks, in order:

  1. `DESIGN.md` is filled in: every required `##` section heading is
     present, each section has at least `_MIN_SECTION_CHARS` characters of
     content (not counting the heading line itself), and no section still
     contains obvious placeholder text (`[fill in`, `TODO`, `...`).
  2. `validate_cp1.py` and `validate_cp2.py` both still exit 0 when
     re-run as fresh subprocesses (`sys.executable`, not imported --
     `grade()` calls `sys.exit` itself, so importing it in-process would
     kill this validator too).

Any failure in either check is `NOT PASSED`, naming which check failed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

REQUIRED_SECTIONS = [
    "Testing pyramid for this stack",
    "What each layer catches",
    "Where mutation testing found gaps",
    "How I'd extend this to CI",
]

_MIN_SECTION_CHARS = 80
_PLACEHOLDER_MARKERS = ("[fill in", "todo")


def _check_design_doc() -> None:
    design_path = TASK_ROOT / "DESIGN.md"
    if not design_path.exists():
        not_passed("DESIGN.md is missing")
    text = design_path.read_text(encoding="utf-8")

    # Split on "## " headings; keep each heading paired with the body text
    # that follows it up to the next "## " heading (or end of file).
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()

    for required in REQUIRED_SECTIONS:
        if required not in sections:
            not_passed(f"DESIGN.md is missing the required '## {required}' section")
        body = sections[required]
        if len(body) < _MIN_SECTION_CHARS:
            not_passed(
                f"DESIGN.md's '## {required}' section is too short "
                f"({len(body)} chars, need at least {_MIN_SECTION_CHARS}) -- fill it in"
            )
        lowered = body.lower()
        for marker in _PLACEHOLDER_MARKERS:
            if marker in lowered:
                not_passed(
                    f"DESIGN.md's '## {required}' section still contains placeholder "
                    f"text ({marker!r}) -- replace it with your own writing"
                )


def _run_validator(name: str) -> None:
    script = TASK_ROOT / "tests" / name
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(TASK_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-10:])
        not_passed(f"{name} did not pass on re-run (exit {proc.returncode}):\n{tail}")


@guarded
def main() -> None:
    _check_design_doc()
    _run_validator("validate_cp1.py")
    _run_validator("validate_cp2.py")
    passed("DESIGN.md filled in, and CP1 + CP2 both still green")


if __name__ == "__main__":
    main()
