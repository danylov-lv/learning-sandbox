"""CP3 validator for the s13 capstone -- design memo + green re-run.

Checks `DESIGN.md` is filled in (all seven required section headings
present, each with real content beyond the shipped '[fill in' placeholder,
a minimum length per section, and the document grounded in this capstone's
actual vocabulary -- honeypots/pacing, the data-quality contract, the
volatile nonce, the budget router, Prometheus, and production scaling),
THEN re-runs `validate_cp1.py` and `validate_cp2.py` as SUBPROCESSES from
the MODULE ROOT and requires both to exit 0. A design memo for a pipeline
that no longer converges, or that regressed on CP2's chaos/change-detection
checks, does not pass this checkpoint either.

The subprocess timeout below is a GENEROUS OUTER SAFETY WRAPPER, not a
performance gate -- CP1/CP2 make no wall-clock assertions of their own, and
a correct-but-slower machine must never fail this checkpoint on time alone.
900s is far beyond what either checkpoint should ever need against this
corpus size; it exists only to catch a genuine hang.

Run from the MODULE ROOT:

    uv run python 07-capstone-data-quality-platform/tests/validate_cp3.py
"""

import re
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import _last_line, guarded, not_passed, passed  # noqa: E402

DESIGN_PATH = TASK_ROOT / "DESIGN.md"

REQUIRED_HEADINGS = [
    "## Architecture and data flow",
    "## Defense handling: headers, honeypots, pacing",
    "## Data-quality contract and quarantine strategy",
    "## Change detection and fingerprint design",
    "## Cost and budget tradeoffs",
    "## Observability",
    "## Scaling to production / 10x",
]

PLACEHOLDER_MARKER = "[fill in"
MIN_SECTION_CONTENT = 220

REQUIRED_KEYWORDS = [
    ("honeypots/pacing", ["honeypot", "pacing", "pace", "token bucket"]),
    ("data-quality contract", ["quarantine", "pandera", "defect"]),
    ("volatile nonce / fingerprint", ["nonce", "fingerprint"]),
    ("budget router", ["render", "review_count", "budget"]),
    ("observability", ["prometheus", "metric", "gauge", "counter", "histogram"]),
    ("scaling", ["scal"]),
]

CP_TIMEOUT = 900  # generous outer safety wrapper -- see module docstring

VALIDATOR_ARGS = {
    "validate_cp1.py": [],
    "validate_cp2.py": [],
}


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


def check_design_doc():
    if not DESIGN_PATH.exists():
        not_passed(f"missing {DESIGN_PATH}")

    text = DESIGN_PATH.read_text(encoding="utf-8")

    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing:
        not_passed(f"DESIGN.md missing required section heading(s): {missing}")

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
            issues.append(f"section '{name}' still contains the shipped '[fill in' placeholder")
        char_count = count_content_chars(content)
        counts[name] = char_count
        if char_count < MIN_SECTION_CONTENT:
            issues.append(f"section '{name}' has only {char_count} chars of content, expected >= {MIN_SECTION_CONTENT}")

    lower_text = text.lower()
    missing_keywords = [label for label, terms in REQUIRED_KEYWORDS if not any(t in lower_text for t in terms)]
    if missing_keywords:
        issues.append(
            f"DESIGN.md doesn't mention required concept(s): {missing_keywords} -- "
            "the memo must be grounded in what this capstone actually built, not generic prose"
        )

    if issues:
        not_passed(f"DESIGN.md: {'; '.join(issues)}")

    return counts


def _run_validator(name):
    script = TASK_ROOT / "tests" / name
    try:
        return subprocess.run(
            ["uv", "run", "python", str(script)] + VALIDATOR_ARGS.get(name, []),
            cwd=str(MODULE_ROOT),
            capture_output=True,
            text=True,
            timeout=CP_TIMEOUT,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"{name} did not exit within {CP_TIMEOUT}s (generous safety wrapper -- likely a hang, not slowness)")


@guarded
def main():
    counts = check_design_doc()

    r1 = _run_validator("validate_cp1.py")
    if r1.returncode != 0:
        not_passed(f"CP1 no longer passes -- fix src/ before finishing the writeup: {_last_line(r1.stdout or r1.stderr)}")

    r2 = _run_validator("validate_cp2.py")
    if r2.returncode != 0:
        not_passed(f"CP2 no longer passes -- fix src/ before finishing the writeup: {_last_line(r2.stdout or r2.stderr)}")

    summary = ", ".join(f"{name}={n} chars" for name, n in counts.items())
    passed(f"DESIGN.md filled ({summary}); CP1 and CP2 both still pass")


if __name__ == "__main__":
    main()
