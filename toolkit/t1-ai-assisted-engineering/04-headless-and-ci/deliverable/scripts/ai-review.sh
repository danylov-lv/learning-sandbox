#!/usr/bin/env bash
# Headless AI review of the working tree's diff against a base ref.
#
# Contract (see the task README for the full spec):
#   - Non-interactive: use `claude -p "<prompt>"`, never bare `claude`.
#   - Build the prompt from `git diff` output (against $1, default
#     "origin/main" if no argument given) -- do not ask the reviewer to
#     paste anything.
#   - Use `--output-format json` so the caller (a human or a CI step) gets
#     a machine-parseable result, not a chat transcript.
#   - Restrict tool access with `--allowedTools` -- this script only needs
#     to read the diff and reason about it, not edit files or run
#     arbitrary commands.
#
# TODO: implement the script per the contract above.

set -euo pipefail

echo "TODO: not implemented" >&2
exit 1
