"""Validator for 04-headless-and-ci. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 04-headless-and-ci/tests/validate.py

Two purely structural gates, no live `claude` call required:
  1. `scripts/ai-review.sh` -- text checks: uses `claude -p` (never a
     bare `claude`), non-interactive, references `--output-format` and
     `git diff`.
  2. `.github/workflows/ai-review.yml` -- YAML-parsed: triggers on a
     pull-request LABEL (not on every push), and has a step that invokes
     `claude` headless.

YAML gotcha this validator has to handle correctly (and that your
workflow file has to survive): PyYAML's default (YAML 1.1) resolver
parses an unquoted `on:` mapping key as the boolean `True`, not the
string `"on"` -- `yaml.safe_load` on any GitHub Actions workflow file
gives you `{True: {...}, "jobs": {...}}`, never `{"on": {...}}`. This
validator reads `workflow.get("on", workflow.get(True))` for exactly
that reason.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed, read_doc  # noqa: E402

SCRIPT_PATH = TASK_DIR / "deliverable" / "scripts" / "ai-review.sh"
WORKFLOW_PATH = TASK_DIR / "deliverable" / ".github" / "workflows" / "ai-review.yml"

_CLAUDE_INVOCATION_RE = re.compile(r"\bclaude\b[^\n]*", re.MULTILINE)
_CLAUDE_DASH_P_RE = re.compile(r"\bclaude\b(?:(?!\n).)*?(?:-p\b|--print\b)")
_INTERACTIVE_RE = re.compile(r"^\s*read\s+", re.MULTILINE)


def _check_script() -> None:
    text = read_doc(SCRIPT_PATH)

    invocations = _CLAUDE_INVOCATION_RE.findall(text)
    invocations = [ln for ln in invocations if not ln.strip().startswith("#")]
    if not invocations:
        not_passed(f"{SCRIPT_PATH}: no 'claude' invocation found")

    non_headless = [ln for ln in invocations if not re.search(r"-p\b|--print\b", ln)]
    if non_headless:
        not_passed(
            f"{SCRIPT_PATH}: found a 'claude' invocation without '-p'/'--print' "
            f"(must always run headless): {non_headless[0].strip()!r}"
        )

    if "--output-format" not in text:
        not_passed(f"{SCRIPT_PATH}: must pass --output-format (e.g. json) for machine-parseable output")

    if "git diff" not in text:
        not_passed(f"{SCRIPT_PATH}: must build its prompt from 'git diff' output, not a pasted/hardcoded diff")

    if _INTERACTIVE_RE.search(text):
        not_passed(f"{SCRIPT_PATH}: contains an interactive 'read' prompt — must be fully non-interactive")

    if "raise NotImplementedError" in text or "TODO: not implemented" in text or 'echo "TODO: not implemented"' in text:
        not_passed(f"{SCRIPT_PATH}: still contains the unfilled stub body")


def _check_workflow() -> None:
    text = read_doc(WORKFLOW_PATH)
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError as e:
        not_passed(f"{WORKFLOW_PATH}: not valid YAML: {e}")
    if not isinstance(workflow, dict):
        not_passed(f"{WORKFLOW_PATH}: must be a YAML mapping at the top level")

    on_value = workflow.get("on", workflow.get(True))
    if on_value is None:
        not_passed(f"{WORKFLOW_PATH}: no 'on:' trigger found")

    if isinstance(on_value, str):
        on_value = {on_value: None}
    if not isinstance(on_value, dict):
        not_passed(f"{WORKFLOW_PATH}: 'on:' must be a mapping of event -> config, got {type(on_value).__name__}")

    if "push" in on_value and "pull_request" not in on_value and "pull_request_target" not in on_value:
        not_passed(
            f"{WORKFLOW_PATH}: triggers on 'push' with no pull_request label trigger — "
            "this must be label-triggered, not run on every push"
        )

    pr_key = "pull_request" if "pull_request" in on_value else "pull_request_target"
    if pr_key not in on_value:
        not_passed(f"{WORKFLOW_PATH}: no 'pull_request' (or 'pull_request_target') trigger found")

    pr_config = on_value[pr_key]
    if not isinstance(pr_config, dict) or "types" not in pr_config:
        not_passed(f"{WORKFLOW_PATH}: '{pr_key}' trigger must specify 'types:' including 'labeled'")

    types = pr_config["types"]
    if not isinstance(types, list) or "labeled" not in types:
        not_passed(f"{WORKFLOW_PATH}: '{pr_key}.types' must include 'labeled' (got {types!r})")

    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        not_passed(f"{WORKFLOW_PATH}: no 'jobs:' found")

    found_claude_step = False
    found_label_condition = False
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_if = str(job.get("if", ""))
        if "label" in job_if.lower():
            found_label_condition = True
        for step in job.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            step_if = str(step.get("if", ""))
            if "label" in step_if.lower():
                found_label_condition = True
            run_val = str(step.get("run", ""))
            uses_val = str(step.get("uses", ""))
            combined = run_val + " " + uses_val
            if "claude" in combined.lower() and ("-p" in combined or "claude-code-action" in combined.lower()):
                found_claude_step = True

    if not found_claude_step:
        not_passed(
            f"{WORKFLOW_PATH}: no step found that invokes claude headless "
            "(a 'run:' containing 'claude ... -p', or a 'uses:' referencing a claude-code action)"
        )

    if not found_label_condition:
        not_passed(
            f"{WORKFLOW_PATH}: no job/step 'if:' condition checks the specific label name — "
            "triggering on ANY label defeats the point of a targeted review step"
        )


@guarded
def main() -> None:
    _check_script()
    _check_workflow()
    passed("ai-review.sh and ai-review.yml both structurally OK")


if __name__ == "__main__":
    main()
