"""Shared pass/fail plumbing and grading helpers for toolkit/t1 validators.

Convention (matches the rest of the repo): a validator prints exactly one
line and exits. On success: `PASSED` (optionally with a trailing detail
line). On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.

Copied from `17-system-design/harness/common.py` (the pass/fail + doc-gate
plumbing) and extended with what this module's behavioral tasks need:

- **Doc gate** (`read_doc`, `parse_sections`, `parse_subsections`,
  `check_sections`, `check_keywords`, `check_quantitative`, `check_answers`):
  unchanged from module 17 — deliverable Markdown/CLAUDE.md files are
  graded structurally, never by content quality.
- **Frontmatter** (`read_frontmatter`): parses a Markdown file's leading
  `---` YAML block, used to grade subagent definition files (task 02).
- **Subprocess grading** (`run_pytest`, `run_hook`): spawn a fresh
  `python -m pytest` subprocess or a hook script subprocess with a JSON
  stdin payload and a timeout, used to behaviorally exercise task 03's
  hook scripts and task 06's learner-authored tests against shipped code.
"""

from __future__ import annotations

import difflib
import functools
import json
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

import yaml

F = TypeVar("F", bound=Callable[..., None])


# --------------------------------------------------------------------------
# Pass / fail plumbing
# --------------------------------------------------------------------------

def not_passed(reason: str) -> NoReturn:
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg: str = "") -> None:
    print(f"PASSED{': ' + msg if msg else ''}")


def _last_line(text: str) -> str:
    """Return the last non-empty line of a text blob (e.g. a formatted
    exception message) — the line closest to "what went wrong" without
    leaking a full traceback to the learner."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line:
            return line
    return "(no error message)"


def guarded(fn: F) -> Callable[..., None]:
    """Wrap a validator's entry point so any uncaught exception becomes a
    single NOT PASSED line instead of a raw traceback.

    Usage:
        @guarded
        def main() -> None:
            ...
            passed()

        if __name__ == "__main__":
            main()
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - intentional catch-all
            text = "".join(traceback.format_exception_only(type(exc), exc))
            not_passed(_last_line(text))

    return wrapper


# --------------------------------------------------------------------------
# Design doc / deliverable doc gate
# --------------------------------------------------------------------------

def read_doc(path) -> str:
    p = Path(path)
    if not p.exists():
        not_passed(f"expected file not found: {p}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        not_passed(f"file is empty: {p}")
    return text


def _parse_headings(text: str, level: int) -> dict:
    """Split text on ATX headings of an exact level (`## ` for level 2,
    `### ` for level 3). A heading of a deeper level (more `#`) never
    matches, since the character right after the marker must be
    whitespace, not another `#`."""
    marker = "#" * level
    pattern = re.compile(r"^" + re.escape(marker) + r"[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()
    return sections


def parse_sections(text: str) -> dict:
    return _parse_headings(text, level=2)


def parse_subsections(text: str) -> dict:
    return _parse_headings(text, level=3)


PLACEHOLDER_MARKERS = ("[fill in", "[FILL IN", "TODO:", "<your answer", "[replace")


def _has_placeholder(body: str) -> bool:
    return any(marker in body for marker in PLACEHOLDER_MARKERS)


def check_no_placeholders(body: str, label: str) -> None:
    if _has_placeholder(body):
        not_passed(f"{label}: still contains a placeholder marker — fill this in")


def check_sections(path, required: list, min_chars) -> dict:
    text = read_doc(path)
    sections = parse_sections(text)

    missing = [h for h in required if h not in sections]
    if missing:
        not_passed(f"missing required section(s): {', '.join(missing)}")

    def _min_for(heading):
        if isinstance(min_chars, dict):
            return min_chars.get(heading, min_chars.get("_default", 0))
        return min_chars

    too_short = []
    for h in required:
        body = sections[h].strip()
        need = _min_for(h)
        if len(body) < need:
            too_short.append(f"'{h}' ({len(body)}/{need} chars)")
    if too_short:
        not_passed(f"section(s) too short: {', '.join(too_short)}")

    for h in required:
        check_no_placeholders(sections[h], f"section '{h}'")

    return sections


def check_keywords(body: str, keywords: list, min_hits: int, label: str) -> None:
    lowered = body.lower()
    hits = {kw for kw in keywords if kw.lower() in lowered}
    if len(hits) < min_hits:
        not_passed(
            f"{label}: found {len(hits)}/{min_hits} required grounding keyword(s) "
            f"among {list(keywords)} (matched: {sorted(hits)})"
        )


_NUMERIC_TOKEN_RE = re.compile(r"\d(?:[\d,_]*\d)?(?:\.\d+)?(?:%|[a-zA-Z]{1,4})?")


def check_quantitative(body: str, min_numbers: int, label: str) -> None:
    tokens = _NUMERIC_TOKEN_RE.findall(body)
    normalized = {t.replace(",", "").replace("_", "").lower() for t in tokens}
    if len(normalized) < min_numbers:
        not_passed(
            f"{label}: found {len(normalized)}/{min_numbers} distinct numeric/quantitative "
            f"tokens — make a quantitative claim (a number, a rate, a size, a percentage)"
        )


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _dedupe_sentences(text: str) -> str:
    """Collapse repeated sentences so padding an answer by restating the same
    filler sentence N times does not read as N sentences of original work."""
    seen, kept = set(), []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.strip()
        if s and s not in seen:
            seen.add(s)
            kept.append(s)
    return " ".join(kept)


def _original_char_count(answer: str, questions_text: str, min_block: int = 40) -> int:
    """Characters of the answer that are NOT copied from the questions doc.

    Both sides are whitespace-normalized first, so re-wrapping a restated
    question does not disguise it. Matching runs shorter than `min_block`
    are left alone — shared technical vocabulary is not plagiarism.
    """
    a = _dedupe_sentences(_normalize_ws(answer))
    q = _normalize_ws(questions_text)
    if not a or not q:
        return len(a)
    matcher = difflib.SequenceMatcher(None, a, q, autojunk=False)
    borrowed = sum(b.size for b in matcher.get_matching_blocks() if b.size >= min_block)
    return max(len(a) - borrowed, 0)


def check_answers(
    path,
    question_ids: list,
    min_answered: int,
    min_chars: int = 200,
    questions_path=None,
    min_original_chars: int = 120,
) -> dict:
    text = read_doc(path)
    subsections = parse_subsections(text)

    questions_text = None
    if questions_path is not None:
        questions_text = read_doc(questions_path)

    problems = []
    answered = 0
    for qid in question_ids:
        body = subsections.get(qid)
        if body is None:
            problems.append(f"{qid} (missing)")
            continue

        stripped = body.strip()
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        question_line = lines[0] if lines else ""

        if _has_placeholder(stripped):
            problems.append(f"{qid} (placeholder)")
            continue
        if questions_text is None and stripped == question_line:
            problems.append(f"{qid} (verbatim copy of the question)")
            continue
        if len(stripped) < min_chars:
            problems.append(f"{qid} (too short: {len(stripped)}/{min_chars} chars)")
            continue
        if questions_text is not None:
            original = _original_char_count(stripped, questions_text)
            if original < min_original_chars:
                problems.append(
                    f"{qid} (mostly restates the question: {original}/{min_original_chars} "
                    "characters of your own)"
                )
                continue

        answered += 1

    if answered < min_answered:
        not_passed(
            f"only {answered}/{min_answered} required subsection(s) genuinely answered; "
            f"unanswered or insufficient: {', '.join(problems) if problems else '(none)'}"
        )

    return subsections


# --------------------------------------------------------------------------
# Frontmatter parsing (subagent definition files)
# --------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)


def read_frontmatter(path) -> tuple[dict, str]:
    """Parse a Markdown file's leading `---`-delimited YAML frontmatter
    block. Returns `(frontmatter_dict, body_text)`. Fails with NOT PASSED
    if the file has no frontmatter block or the block is not valid YAML
    mapping."""
    text = read_doc(path)
    m = _FRONTMATTER_RE.match(text)
    if not m:
        not_passed(f"{path}: no YAML frontmatter block (must start with '---')")
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        not_passed(f"{path}: frontmatter is not valid YAML: {e}")
    if not isinstance(data, dict):
        not_passed(f"{path}: frontmatter must be a YAML mapping, got {type(data).__name__}")
    body = text[m.end():].strip()
    return data, body


# --------------------------------------------------------------------------
# Subprocess grading helpers
# --------------------------------------------------------------------------

_SUMMARY_COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)")
_SUMMARY_SCAN_LINES = 5
_TAIL_LINES = 40


def _parse_collected(output: str) -> int:
    summary_area = "\n".join(output.splitlines()[-_SUMMARY_SCAN_LINES:])
    return sum(int(n) for n, _ in _SUMMARY_COUNT_RE.findall(summary_area))


def _tail(output: str, n: int = _TAIL_LINES) -> str:
    lines = output.splitlines()
    return "\n".join(lines[-n:])


@dataclass
class PytestResult:
    passed: bool
    returncode: int
    collected: int
    output_tail: str
    timed_out: bool = False


def run_pytest(test_paths: list, cwd, timeout: int = 60, extra_args: list | None = None) -> PytestResult:
    """Run `python -m pytest <test_paths>` in a fresh subprocess, using
    `sys.executable` (never a bare `python` on PATH — see the Windows
    gotcha documented in module 16: a bare `python` inside a subprocess
    can resolve to a different interpreter than this project's venv)."""
    cmd = [sys.executable, "-m", "pytest", *test_paths, "-q"]
    if extra_args:
        cmd.extend(extra_args)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        return PytestResult(
            passed=False,
            returncode=-1,
            collected=_parse_collected(stdout or ""),
            output_tail=_tail((stdout or "") + f"\n[TIMEOUT after {timeout}s]"),
            timed_out=True,
        )
    output = proc.stdout + proc.stderr
    return PytestResult(
        passed=proc.returncode == 0,
        returncode=proc.returncode,
        collected=_parse_collected(output),
        output_tail=_tail(output),
    )


@dataclass
class HookResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    decision_json: dict | None = None


def run_hook(
    command: list,
    payload: dict,
    cwd,
    env: dict | None = None,
    timeout: int = 30,
) -> HookResult:
    """Invoke a hook script as a subprocess, feeding `payload` as JSON on
    stdin (the shape Claude Code sends a hook command), and capture its
    exit code and stdout/stderr. If stdout parses as JSON, it is also
    exposed as `.decision_json` so a caller can check for
    `{"decision": "block", ...}` without re-parsing.
    """
    import os as _os

    full_env = _os.environ.copy()
    if env:
        full_env.update(env)

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
        )
    except subprocess.TimeoutExpired:
        return HookResult(returncode=-1, stdout="", stderr=f"[TIMEOUT after {timeout}s]", timed_out=True)

    decision_json = None
    stdout_stripped = proc.stdout.strip()
    if stdout_stripped:
        try:
            candidate = json.loads(stdout_stripped)
            if isinstance(candidate, dict):
                decision_json = candidate
        except json.JSONDecodeError:
            pass

    return HookResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        decision_json=decision_json,
    )
