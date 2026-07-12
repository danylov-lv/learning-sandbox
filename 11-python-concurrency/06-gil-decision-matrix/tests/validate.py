"""Validator for 11-python-concurrency task 06 -- gil-decision-matrix.

Two independent things must be true, checked in this order:

1. `baseline-local.json` (written by `uv run python baseline.py`, which
   depends on your `src/runners.py` implementation) shows the relative
   timing relationships the GIL predicts on a real multi-core machine:
   ProcessPoolExecutor gives a meaningful speedup over sequential for
   `cpu_bound` (separate GIL per process -> real parallelism), while
   ThreadPoolExecutor does not (one GIL, one thread of Python bytecode at a
   time); both ThreadPoolExecutor and asyncio give a large speedup over
   sequential for `io_bound` (`time.sleep()` releases the GIL). Every
   threshold below is a RELATIVE comparison against your own machine's
   sequential run -- never an absolute wall-clock number -- with margins
   chosen from repeated measurement on a 12-core dev machine, wide enough
   to not be flaky on a slower or busier machine.
2. `ANSWER.md` is filled in with your own analysis grounded in those
   numbers -- not left as the shipped template.

Run from this task's directory:

    uv run python tests/validate.py
"""

import re
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed, read_baseline  # noqa: E402

BASELINE_PATH = "06-gil-decision-matrix/baseline-local.json"
ANSWER_PATH = TASK_ROOT / "ANSWER.md"

# --------------------------------------------------------------------------
# Timing margins -- relative only, measured with headroom (see NOTES in the
# task README for the actual numbers observed while authoring this task).
# --------------------------------------------------------------------------

MIN_PROCESS_SPEEDUP = 1.5   # processes must beat sequential by >= 1.5x on cpu_bound
MAX_THREAD_SPEEDUP = 1.3    # threads must stay close to parity on cpu_bound (GIL-bound)
MIN_SPEEDUP_GAP = 1.0       # process speedup must exceed thread speedup by this much

MIN_IO_CONCURRENT_SPEEDUP = 3.0  # both threads and asyncio must solidly beat sequential on io_bound

REQUIRED_HEADINGS = [
    "## Decision matrix",
    "## CPU-bound: why threads don't help",
    "## I/O-bound: why the GIL doesn't matter here",
    "## Process pool overhead: when it isn't worth it",
    "## Rules of thumb",
]

GROUNDING_KEYWORDS = {
    "gil": ["gil"],
    "multiprocessing": ["multiprocessing", "process pool", "processpoolexecutor"],
    "threading": ["threadpoolexecutor", "thread pool", "threading"],
    "cpu_bound": ["cpu-bound", "cpu bound"],
    "io_bound": ["io-bound", "io bound"],
    "pickle": ["pickl"],
}
MIN_GROUNDING_HITS = 4

PLACEHOLDER_MARKER = "[fill in"
MIN_SECTION_CONTENT = 150  # minimum chars of actual content per section


# --------------------------------------------------------------------------
# Timing checks
# --------------------------------------------------------------------------

def check_timings(baseline):
    cpu = baseline.get("cpu_bound", {})
    io = baseline.get("io_bound", {})

    missing_cpu = [k for k in ("sequential", "threads", "processes") if k not in cpu]
    if missing_cpu:
        return False, f"baseline-local.json missing cpu_bound key(s): {missing_cpu}"
    missing_io = [k for k in ("sequential", "threads", "asyncio") if k not in io]
    if missing_io:
        return False, f"baseline-local.json missing io_bound key(s): {missing_io}"

    for section, keys in (("cpu_bound", cpu), ("io_bound", io)):
        for k in keys:
            v = keys[k]
            if not isinstance(v, (int, float)) or v <= 0:
                return False, f"baseline-local.json {section}.{k} is not a positive number: {v!r}"

    process_speedup = cpu["sequential"] / cpu["processes"]
    thread_speedup = cpu["sequential"] / cpu["threads"]

    if process_speedup < MIN_PROCESS_SPEEDUP:
        return False, (
            f"cpu_bound process speedup {process_speedup:.2f}x is below the required "
            f"{MIN_PROCESS_SPEEDUP}x -- ProcessPoolExecutor isn't parallelizing cpu_bound "
            f"the way it should (check run_processes actually uses a ProcessPoolExecutor "
            f"and BATCH_SIZE calls are genuinely handed to it)"
        )
    if thread_speedup > MAX_THREAD_SPEEDUP:
        return False, (
            f"cpu_bound thread speedup {thread_speedup:.2f}x is above {MAX_THREAD_SPEEDUP}x "
            f"-- suspiciously high for GIL-bound pure-Python work; check run_threads isn't "
            f"accidentally parallelizing (e.g. calling into numpy or another GIL-releasing op)"
        )
    if process_speedup - thread_speedup < MIN_SPEEDUP_GAP:
        return False, (
            f"cpu_bound process speedup ({process_speedup:.2f}x) is not meaningfully greater "
            f"than thread speedup ({thread_speedup:.2f}x) -- the gap the GIL should produce "
            f"between processes and threads on CPU-bound work isn't showing up"
        )

    io_thread_speedup = io["sequential"] / io["threads"]
    io_asyncio_speedup = io["sequential"] / io["asyncio"]

    if io_thread_speedup < MIN_IO_CONCURRENT_SPEEDUP:
        return False, (
            f"io_bound thread speedup {io_thread_speedup:.2f}x is below the required "
            f"{MIN_IO_CONCURRENT_SPEEDUP}x -- ThreadPoolExecutor should heavily overlap "
            f"time.sleep() calls since sleep releases the GIL"
        )
    if io_asyncio_speedup < MIN_IO_CONCURRENT_SPEEDUP:
        return False, (
            f"io_bound asyncio speedup {io_asyncio_speedup:.2f}x is below the required "
            f"{MIN_IO_CONCURRENT_SPEEDUP}x -- run_asyncio should run the batch concurrently, "
            f"not await each call one at a time"
        )

    return True, {
        "process_speedup": process_speedup,
        "thread_speedup": thread_speedup,
        "io_thread_speedup": io_thread_speedup,
        "io_asyncio_speedup": io_asyncio_speedup,
    }


# --------------------------------------------------------------------------
# ANSWER.md writeup gating (same pattern as the module's writeup tasks)
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
            issues.append(
                f"section '{name}' has only {char_count} chars of content, "
                f"expected at least {MIN_SECTION_CONTENT} (looks unfilled)"
            )

    if issues:
        return False, "; ".join(issues), counts
    return True, "", counts


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
    baseline = read_baseline(BASELINE_PATH)
    if baseline is None:
        not_passed(
            f"{BASELINE_PATH} not found -- run `uv run python baseline.py` first "
            f"(requires src/runners.py to be implemented)"
        )

    ok, result = check_timings(baseline)
    if not ok:
        not_passed(result)
    speedups = result

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

    passed(
        f"process speedup={speedups['process_speedup']:.2f}x, "
        f"thread speedup={speedups['thread_speedup']:.2f}x, "
        f"io thread speedup={speedups['io_thread_speedup']:.2f}x, "
        f"io asyncio speedup={speedups['io_asyncio_speedup']:.2f}x; "
        f"ANSWER.md filled"
    )


if __name__ == "__main__":
    main()
