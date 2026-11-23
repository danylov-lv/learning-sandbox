#!/usr/bin/env python3
"""Read a Codex PostToolUse payload and check the project at payload['cwd'].

Use the current interpreter. On success, exit 0 without block feedback.
On a failed check, return decision:block with a non-empty reason at exit 0,
or exit 2 with a non-empty feedback message on stderr. Do not undo edits.
"""

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    raise NotImplementedError("read payload, run pytest via sys.executable, report result")


if __name__ == "__main__":
    main()
