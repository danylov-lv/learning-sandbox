"""Validator for 03-hooks-and-guardrails. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 03-hooks-and-guardrails/tests/validate.py

Two gates:
  1. Structural: settings.json has a PostToolUse entry per hook whose
     matcher regex actually matches both "Edit" and "Write", and whose
     command references the required hook script filename.
  2. Behavioral: each hook script is invoked as a real subprocess against
     a PASSING and a FAILING fixture project, feeding a realistic
     PostToolUse JSON payload on stdin. A hook signals failure either by
     a non-zero exit code or by printing {"decision": "block", ...} JSON
     to stdout; either signal is accepted, matching the real range of
     valid hook behavior.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed, run_hook  # noqa: E402

DELIVERABLE_DIR = TASK_DIR / "deliverable"
SETTINGS_PATH = DELIVERABLE_DIR / ".claude" / "settings.json"
HOOKS_DIR = DELIVERABLE_DIR / ".claude" / "hooks"
FIXTURES_DIR = TASK_DIR / "tests" / "fixtures"

REQUIRED_HOOK_FILES = {
    "run-tests": "run-tests.py",
    "lint": "lint.py",
}

HOOK_TIMEOUT = 30

_SCRIPT_TOKEN_RE = re.compile(r'"?([^"\s]+\.py)"?')


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        not_passed(f"settings.json not found: {SETTINGS_PATH}")
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        not_passed(f"settings.json is not valid JSON: {e}")
    if not isinstance(data, dict):
        not_passed("settings.json must be a JSON object")
    return data


def _post_tool_use_entries(settings: dict) -> list:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        not_passed("settings.json missing top-level 'hooks' object")
    entries = hooks.get("PostToolUse")
    if not isinstance(entries, list) or not entries:
        not_passed("settings.json missing a non-empty 'hooks.PostToolUse' array")
    return entries


def _matcher_matches_edit_and_write(matcher: str) -> bool:
    try:
        return bool(re.fullmatch(matcher, "Edit")) and bool(re.fullmatch(matcher, "Write"))
    except re.error:
        return False


def _extract_script_path(command: str) -> Path | None:
    m = _SCRIPT_TOKEN_RE.search(command)
    if not m:
        return None
    token = m.group(1)
    token = token.replace("$CLAUDE_PROJECT_DIR", str(DELIVERABLE_DIR)).replace(
        "${CLAUDE_PROJECT_DIR}", str(DELIVERABLE_DIR)
    )
    return Path(token)


def _find_hook_entry(entries: list, required_filename: str) -> tuple[str, str]:
    """Return (matcher, command) of the PostToolUse entry whose command
    references `required_filename`."""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        matcher = entry.get("matcher")
        sub_hooks = entry.get("hooks")
        if not isinstance(sub_hooks, list):
            continue
        for h in sub_hooks:
            if not isinstance(h, dict) or h.get("type") != "command":
                continue
            command = h.get("command", "")
            script_path = _extract_script_path(command)
            if script_path is not None and script_path.name == required_filename:
                return matcher, command
    not_passed(
        f"no PostToolUse hook entry found whose command references '{required_filename}' "
        f"under .claude/hooks/ (required filename, see README)"
    )


def _check_matcher(matcher, label: str) -> None:
    if not isinstance(matcher, str) or not matcher.strip():
        not_passed(f"{label}: matcher must be a non-empty string")
    if not _matcher_matches_edit_and_write(matcher):
        not_passed(f"{label}: matcher '{matcher}' does not match both 'Edit' and 'Write'")


def _run_hook_scenario(script_path: Path, project_dir: Path, edited_file: Path, label: str):
    if not script_path.exists():
        not_passed(f"{label}: hook script not found: {script_path}")
    payload = {
        "session_id": "validator-session",
        "hook_event_name": "PostToolUse",
        "cwd": str(project_dir),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(edited_file)},
    }
    result = run_hook(
        [sys.executable, str(script_path)],
        payload,
        cwd=project_dir,
        env={"CLAUDE_PROJECT_DIR": str(project_dir)},
        timeout=HOOK_TIMEOUT,
    )
    if result.timed_out:
        not_passed(f"{label}: hook script timed out after {HOOK_TIMEOUT}s")
    return result


def _signals_block(result) -> bool:
    if result.returncode != 0:
        return True
    if result.decision_json and result.decision_json.get("decision") == "block":
        return True
    return False


@guarded
def main() -> None:
    settings = _load_settings()
    entries = _post_tool_use_entries(settings)
    if len(entries) < 2:
        not_passed(f"settings.json has {len(entries)} PostToolUse entr(y/ies), need at least 2")

    run_tests_matcher, _ = _find_hook_entry(entries, REQUIRED_HOOK_FILES["run-tests"])
    lint_matcher, _ = _find_hook_entry(entries, REQUIRED_HOOK_FILES["lint"])
    _check_matcher(run_tests_matcher, "run-tests.py hook entry")
    _check_matcher(lint_matcher, "lint.py hook entry")

    run_tests_script = HOOKS_DIR / REQUIRED_HOOK_FILES["run-tests"]
    lint_script = HOOKS_DIR / REQUIRED_HOOK_FILES["lint"]

    passing_proj = FIXTURES_DIR / "tests-passing"
    failing_proj = FIXTURES_DIR / "tests-failing"

    r_pass = _run_hook_scenario(
        run_tests_script, passing_proj, passing_proj / "tests" / "test_sample.py", "run-tests.py (passing fixture)"
    )
    if _signals_block(r_pass):
        not_passed(
            "run-tests.py signaled failure (non-zero exit or decision:block) against a PASSING "
            f"test project — it must exit 0 with no block decision. stdout={r_pass.stdout!r} "
            f"stderr_tail={r_pass.stderr[-500:]!r}"
        )

    r_fail = _run_hook_scenario(
        run_tests_script, failing_proj, failing_proj / "tests" / "test_sample.py", "run-tests.py (failing fixture)"
    )
    if not _signals_block(r_fail):
        not_passed(
            "run-tests.py did not signal failure (exit 0, no decision:block) against a FAILING "
            f"test project — it must either exit non-zero or print a decision:block JSON. "
            f"stdout={r_fail.stdout!r} stderr_tail={r_fail.stderr[-500:]!r}"
        )

    clean_proj = FIXTURES_DIR / "lint-clean"
    dirty_proj = FIXTURES_DIR / "lint-dirty"

    l_clean = _run_hook_scenario(lint_script, clean_proj, clean_proj / "sample.py", "lint.py (clean fixture)")
    if _signals_block(l_clean):
        not_passed(
            "lint.py signaled failure against a CLEAN file — it must exit 0 with no block decision. "
            f"stdout={l_clean.stdout!r} stderr_tail={l_clean.stderr[-500:]!r}"
        )

    l_dirty = _run_hook_scenario(lint_script, dirty_proj, dirty_proj / "sample.py", "lint.py (dirty fixture)")
    if not _signals_block(l_dirty):
        not_passed(
            "lint.py did not signal failure against a file with real ruff violations — it must "
            f"either exit non-zero or print a decision:block JSON. stdout={l_dirty.stdout!r} "
            f"stderr_tail={l_dirty.stderr[-500:]!r}"
        )

    passed("settings.json structure OK; both hooks behaviorally verified pass/fail on 4 fixtures")


if __name__ == "__main__":
    main()
