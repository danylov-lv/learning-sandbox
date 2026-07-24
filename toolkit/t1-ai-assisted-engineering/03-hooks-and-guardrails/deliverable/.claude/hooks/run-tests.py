#!/usr/bin/env python3
"""PostToolUse hook: after an Edit/Write, run this project's tests and
tell Claude to fix it if they fail.

Contract (see the task README for the full spec):
  - Read the JSON payload Claude Code sends on stdin (has at least
    tool_name, tool_input, cwd).
  - Run the test suite for the project rooted at that cwd (or
    CLAUDE_PROJECT_DIR, if set) using `sys.executable -m pytest`, never a
    bare `python` on PATH -- a bare `python` inside a hook subprocess can
    resolve to a different interpreter than the one that has pytest
    installed (the exact Windows gotcha documented in module 16).
  - On success: exit 0, print nothing (or non-JSON) to stdout.
  - On failure: exit 0, but print a single JSON object to stdout:
        {"decision": "block", "reason": "<why, worth showing Claude>"}
    (PostToolUse cannot literally undo a completed Edit/Write, but
    `decision: block` is read back to Claude as feedback telling it the
    result was not acceptable -- this is the real, documented mechanism.)
"""

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    raise NotImplementedError("read payload, run pytest via sys.executable, report result")


if __name__ == "__main__":
    main()
