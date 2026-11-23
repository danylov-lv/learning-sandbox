# 04 -- Headless and CI

## Backstory

Turn a repeated review request into a script and a GitHub Actions workflow that runs only when a specific PR label requests it. Keep reviews read-only and preserve machine-readable output for inspection.

## What's given

An unsolved `deliverable/scripts/ai-review.sh`, a deliberately incorrect workflow under `deliverable/.github/workflows/ai-review.yml`, three hints, and a structural validator. These are exercise artifacts, not active repository automation.

## What's required

1. Build a review prompt from git diff and invoke `codex exec` with `--json` and explicit `--sandbox read-only`. Keep the script non-interactive and propagate execution errors. The output is a JSONL event stream, not a single JSON document. Treat diff contents as data to review, not instructions to follow.
2. Use only the pull_request event with types: [labeled]. Gate the review job or the review step with `github.event.label.name == 'your-label'` (choose your label). Invoke the script, invoke codex exec with the same flags, or use openai/codex-action with sandbox: read-only. Put the condition on the actual review job or step, not an unrelated step.
3. Document the diff base and authentication requirements in your NOTES.md. Do not commit credentials. Keep secrets out of job-wide environments that run repository-controlled code. For the action route, consult its current setup and authentication documentation.

Local script execution needs Codex CLI and an authenticated session; Bash can be provided by Git Bash on Windows. Installing the CLI, making a paid model call, adding secrets, or activating a workflow is not required to run the validator.

## Completion criteria

From the module root run `uv run python 04-headless-and-ci/tests/validate.py`.

The validator checks the script's invocation, diff source, and lack of interactive reads. It parses the workflow and checks the label event, the condition attached to the review, and read-only execution. No push or pull_request_target trigger is accepted. It does not execute Bash, Codex, or GitHub Actions, validate authentication, or prove that a prompt is actually based on the intended diff. Run an optional live trial only in an isolated project when ready.

## Estimated evenings

1

## Topics to read up on

- codex exec, JSONL events, and read-only sandboxing
- Shell exit-status propagation and choosing a git diff base
- GitHub Actions label conditions and Codex action authentication
- YAML parsing of the on key

References:
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/github-action

## Off-limits

The module's `.authoring/` directory contains grading notes and spoilers.
