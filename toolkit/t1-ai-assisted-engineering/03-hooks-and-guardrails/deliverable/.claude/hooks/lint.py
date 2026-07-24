#!/usr/bin/env python3
"""PostToolUse hook: after an Edit/Write, run `ruff check` and tell Claude
to fix it if there are lint violations.

Contract (see the task README for the full spec):
  - Read the JSON payload Claude Code sends on stdin.
  - Run `ruff check` against the project rooted at cwd (or
    CLAUDE_PROJECT_DIR). `ruff` is a standalone tool on PATH in this
    environment -- invoke it directly (e.g. via subprocess), not through
    a Python interpreter.
  - On success (no violations): exit 0, print nothing (or non-JSON) to
    stdout.
  - On failure (violations found): exit 0, but print a single JSON
    object to stdout: {"decision": "block", "reason": "<ruff's findings>"}
"""

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    raise NotImplementedError("read payload, run ruff check, report result")


if __name__ == "__main__":
    main()
