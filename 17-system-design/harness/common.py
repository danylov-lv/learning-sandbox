"""Shared pass/fail plumbing and doc/estimate checks for module 17 validators.

Convention (matches the rest of the repo): a validator prints exactly one
line and exits. On success: `PASSED` (optionally with a trailing detail
line). On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.

Two families of checks live here, matching the module's two grading gates:

- **Design-doc structure** (`read_doc`, `parse_sections`, `parse_subsections`,
  `check_sections`, `check_keywords`, `check_quantitative`, `check_answers`):
  DESIGN.md is graded structurally, never by content quality — required
  `##` sections exist and meet a minimum length, no leftover placeholder
  markers, grounding keywords appear, quantitative claims are present, and
  the hostile-review `### Qn` subsections are actually answered.
- **Capacity model** (`load_workload`, `check_close`, `import_estimate`,
  `check_estimate_module`): `src/estimate.py` is graded numerically against
  an independent recomputation the validator performs itself, across
  multiple perturbed workloads — never by string/AST inspection.
"""

from __future__ import annotations

import difflib
import functools
import importlib.util
import json
import math
import re
import sys
import traceback
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

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
# Capacity model: workload loading and numeric comparison
# --------------------------------------------------------------------------

def load_workload(path) -> dict:
    p = Path(path)
    if not p.exists():
        not_passed(f"workload file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        not_passed(f"could not read workload file {p}: {e}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        not_passed(f"workload file {p} is not valid JSON: {e}")
    if not isinstance(data, dict):
        not_passed(f"workload file {p} must contain a JSON object, got {type(data).__name__}")
    return data


def check_close(actual, expected, rel_tol: float = 1e-6, label: str = "value") -> None:
    if actual is None or isinstance(actual, bool) or not isinstance(actual, (int, float)):
        not_passed(f"{label}: expected a number, got {actual!r}")
    if isinstance(actual, float) and math.isnan(actual):
        not_passed(f"{label}: got NaN, expected {expected!r}")
    if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=1e-9):
        not_passed(f"{label}: got {actual!r}, expected {expected!r} (rel_tol={rel_tol})")


# --------------------------------------------------------------------------
# Capacity model: importing the learner's src/estimate.py
# --------------------------------------------------------------------------

def import_estimate(task_dir, module_path: str = "src/estimate.py", name: str = "estimate"):
    p = Path(task_dir) / module_path
    if not p.exists():
        not_passed(f"{module_path} not found in {task_dir}")
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        not_passed(f"could not load module spec for {p}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, SyntaxError) as e:
        not_passed(f"failed to import {module_path}: {type(e).__name__}: {e}")
    return module


def check_estimate_module(module, required_callables: list) -> None:
    missing = [name for name in required_callables if not callable(getattr(module, name, None))]
    if missing:
        not_passed(f"src/estimate.py is missing required callable(s): {', '.join(missing)}")


# --------------------------------------------------------------------------
# Design doc: reading and section parsing
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
) -> None:
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
            # Weak fallback: without the questions doc all we can catch is a
            # single-line body identical to its own first line. Pass
            # `questions_path` instead — it compares against the real
            # question text, re-wrapped or not.
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
            f"only {answered}/{min_answered} required hostile-review question(s) answered; "
            f"unanswered or insufficient: {', '.join(problems) if problems else '(none)'}"
        )
