# 03 -- Hooks and Guardrails

## Backstory

An edit can look plausible while breaking tests or style checks. Add deterministic feedback after Codex edits, so a failed check becomes visible immediately. A PostToolUse hook runs after the edit and cannot undo it.

## What's given

- `deliverable/.codex/hooks.json` wires synchronous handlers to file edits through apply_patch.
- `.codex/hooks/run-tests.py` and `.codex/hooks/lint.py` inside deliverable are unsolved scripts.
- Four fixture projects cover passing/failing tests and clean/dirty lint.
- The validator invokes hooks directly as subprocesses; no model call is required.

## What's required

Implement both scripts. Read JSON from stdin and use its cwd as the project root. Run pytest or ruff check using the current interpreter (`sys.executable -m ...`). The module installs both tools. Resolve the project from the input payload rather than a provider-specific environment variable.

On success, exit 0 without block feedback. On a failed check, either emit a JSON object with decision `block` and a non-empty reason while exiting 0, or exit 2 with a non-empty feedback message on stderr. A crash with exit 1 is not valid hook feedback. Keep diagnostics concise.

Keep hooks synchronous. Commands in hooks.json must reference `.codex/hooks/run-tests.py` and `.codex/hooks/lint.py` relative to the project root. The matcher must match apply_patch or both Edit/Write aliases. The actual payload uses tool_name `apply_patch` and tool_input.command containing patch text, not a file_path field. These exercises run from an isolated project's root.

For an optional live trial, copy the completed .codex directory into a temporary fixture project and launch a local Codex session there. Do not activate these hooks in the sandbox itself. Cloud orchestration may not support local command hooks; the direct subprocess checks still work.

## Completion criteria

From the module root run `uv run python 03-hooks-and-guardrails/tests/validate.py`.

It checks hook configuration and exercises both scripts against real passing/failing fixture projects. Clean fixtures must exit 0; bad fixtures must produce documented block feedback. Timeouts and infrastructure errors fail. Fixtures must remain unchanged. A passing validator does not certify a live Codex session.

## Estimated evenings

1

## Topics to read up on

- PostToolUse timing and feedback versus undoing edits
- hooks.json discovery, synchronous handlers, and matcher aliases
- JSON stdin, cwd, subprocess return codes, and interpreter selection
- Differences between local and cloud orchestration

Reference: https://learn.chatgpt.com/docs/hooks

## Off-limits

The module's `.authoring/` directory contains grading notes and spoilers.
