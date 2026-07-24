"""Validator for 04-hyperfine-benchmark. Run from the module root:

    cd toolkit/t3-cli-data-toolkit
    uv run python 04-hyperfine-benchmark/tests/validate.py

Runs src/benchmark.sh (which itself runs hyperfine and exports JSON),
parses that JSON, and checks ANSWER.md's stated winner against whichever
command actually had the lower mean in the JSON. No absolute timing
threshold is ever asserted -- only agreement between what the learner
claimed and what their own measurement showed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed, run_script  # noqa: E402

RESULTS_PATH = TASK_DIR / "results.json"
ANSWER_PATH = TASK_DIR / "ANSWER.md"

PLACEHOLDER_RE = re.compile(r"\[fill in", re.IGNORECASE)


def _check_warmup_flag(script_path: Path) -> None:
    text = script_path.read_text(encoding="utf-8")
    if not re.search(r"--warmup(?:[= ]|\s+)\d+", text):
        not_passed("src/benchmark.sh does not appear to pass --warmup <N> to hyperfine")


def _load_results() -> list:
    if not RESULTS_PATH.exists():
        not_passed(
            f"{RESULTS_PATH.relative_to(MODULE_ROOT)} not found -- src/benchmark.sh must "
            "call hyperfine with --export-json 04-hyperfine-benchmark/results.json"
        )
    try:
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        not_passed(f"{RESULTS_PATH.name} is not valid JSON: {e}")
    results = data.get("results")
    if not isinstance(results, list) or len(results) < 2:
        not_passed(f"{RESULTS_PATH.name}: expected >=2 commands under 'results', found {results!r}")
    if len(results) != 2:
        not_passed(
            f"{RESULTS_PATH.name}: this task's A/B answer scheme needs exactly 2 commands, "
            f"found {len(results)}"
        )
    for i, r in enumerate(results):
        if not isinstance(r, dict) or "mean" not in r or "command" not in r:
            not_passed(f"{RESULTS_PATH.name}: result {i} is missing 'command'/'mean'")
        if not isinstance(r.get("times"), list) or not r["times"]:
            not_passed(f"{RESULTS_PATH.name}: result {i} has no recorded 'times'")
    return results


def _parse_answer() -> tuple:
    if not ANSWER_PATH.exists():
        not_passed(f"{ANSWER_PATH.name} not found")
    text = ANSWER_PATH.read_text(encoding="utf-8")

    winner_m = re.search(r"^Winner:\s*(\S+)", text, re.MULTILINE)
    if not winner_m or winner_m.group(1).strip().upper() not in ("A", "B"):
        not_passed(f"{ANSWER_PATH.name}: 'Winner:' line must say exactly 'A' or 'B'")
    winner = winner_m.group(1).strip().upper()

    relative_m = re.search(r"^Relative:\s*(.+)$", text, re.MULTILINE)
    if not relative_m or not relative_m.group(1).strip() or PLACEHOLDER_RE.search(relative_m.group(1)):
        not_passed(f"{ANSWER_PATH.name}: 'Relative:' line is missing or still a placeholder")

    why_m = re.search(r"^## Why\s*\n+(.*)", text, re.MULTILINE | re.DOTALL)
    why_body = why_m.group(1).strip() if why_m else ""
    if PLACEHOLDER_RE.search(why_body) or len(why_body) < 15:
        not_passed(f"{ANSWER_PATH.name}: '## Why' section is missing, a placeholder, or too short")

    return winner, text


@guarded
def main() -> None:
    script_path = TASK_DIR / "src" / "benchmark.sh"
    _check_warmup_flag(script_path)

    if RESULTS_PATH.exists():
        RESULTS_PATH.unlink()

    result = run_script(script_path, cwd=MODULE_ROOT, timeout=180.0)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        not_passed(f"src/benchmark.sh exited {result.returncode}: {tail}")

    results = _load_results()
    winner_stated, _ = _parse_answer()

    means = [r["mean"] for r in results]
    actual_winner = "A" if means[0] < means[1] else "B"

    if winner_stated != actual_winner:
        not_passed(
            f"ANSWER.md says Winner: {winner_stated}, but results.json shows "
            f"'{results[0]['command']}' (mean {means[0]:.6f}s) vs "
            f"'{results[1]['command']}' (mean {means[1]:.6f}s) -- "
            f"the actually faster one is {actual_winner}"
        )

    passed(f"Winner {winner_stated} confirmed against results.json (mean {means[0]:.4f}s vs {means[1]:.4f}s)")


if __name__ == "__main__":
    main()
