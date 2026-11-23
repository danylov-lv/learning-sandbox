"""Structural checks for the Codex review script and label-gated workflow.

These checks do not execute Codex, authenticate, or publish a workflow.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed, read_doc

SCRIPT_PATH = TASK_DIR / "deliverable/scripts/ai-review.sh"
WORKFLOW_PATH = TASK_DIR / "deliverable/.github/workflows/ai-review.yml"
_INVOCATION = re.compile(r"\bcodex[ \t]+([^\n]*)")
_LABEL = re.compile(r"github\.event\.label\.name\s*==\s*(['\"])([^'\"]+)\1")


def _code(text: str) -> str:
    return "\n".join(line for line in text.replace("\\\n", " ").splitlines() if not line.lstrip().startswith("#"))


def _check_invocations(text: str) -> bool:
    invocations = _INVOCATION.findall(_code(text))
    for args in invocations:
        if not re.match(r"exec\b", args):
            not_passed("use codex exec rather than an interactive Codex invocation")
        if not re.search(r"--json\b", args):
            not_passed("codex exec must use --json for a JSONL event stream")
        sandboxes = re.findall(r"--sandbox(?:=|\s+)['\"]?([a-z-]+)", args)
        if not sandboxes or any(value != "read-only" for value in sandboxes):
            not_passed("codex exec must explicitly use --sandbox read-only without overrides")
        if re.search(r"--(?:dangerously-bypass-approvals-and-sandbox|yolo|full-auto|approve-for-me)\b", args):
            not_passed("review invocations must retain read-only execution")
    return bool(invocations)


def _check_script() -> None:
    text = _code(read_doc(SCRIPT_PATH))
    if "TODO: not implemented" in text:
        not_passed("ai-review.sh still contains its unsolved stub")
    if not _check_invocations(text):
        not_passed("ai-review.sh must invoke codex exec")
    if "git diff" not in text:
        not_passed("build the review prompt from git diff")
    if re.search(r"^\s*read\s+", text, re.MULTILINE):
        not_passed("ai-review.sh must be non-interactive")


def _check_workflow() -> None:
    try:
        workflow = yaml.safe_load(read_doc(WORKFLOW_PATH))
    except yaml.YAMLError as exc:
        not_passed(f"invalid workflow YAML: {exc}")
    if not isinstance(workflow, dict):
        not_passed("workflow must be a mapping")
    events = workflow.get("on", workflow.get(True))
    if not isinstance(events, dict) or set(events) != {"pull_request"}:
        not_passed("use only pull_request with types: [labeled], not push or pull_request_target")
    event = events["pull_request"]
    if not isinstance(event, dict) or event.get("types") != ["labeled"]:
        not_passed("pull_request.types must be [labeled]")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        not_passed("workflow must define jobs")
    found = False
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            not_passed("job steps must be a list")
        for step in steps:
            if not isinstance(step, dict):
                continue
            run = str(step.get("run", ""))
            action = str(step.get("uses", "")).startswith("openai/codex-action@")
            script = bool(re.search(r"(?:^|[\s/])ai-review\.sh\b", _code(run)))
            direct = _check_invocations(run)
            if not (action or script or direct):
                continue
            if action:
                options = step.get("with", {})
                if not isinstance(options, dict) or options.get("sandbox") != "read-only":
                    not_passed("the Codex action must set sandbox: read-only")
            if script:
                _check_script()
            if not any(_LABEL.search(str(condition)) for condition in (job.get("if", ""), step.get("if", ""))):
                not_passed("the review job or review step must check github.event.label.name == a specific label")
            found = True
    if not found:
        not_passed("workflow must run the review script, codex exec, or openai/codex-action")


@guarded
def main() -> None:
    _check_script()
    _check_workflow()
    passed("Codex script and label-gated workflow are structurally valid; live execution not checked")


if __name__ == "__main__":
    main()
