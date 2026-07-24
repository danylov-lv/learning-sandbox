"""A minimal stdio MCP server exposing sandbox progress.

Contract (see the task README for the full spec):
  - Build the server with `mcp.server.fastmcp.FastMCP`.
  - Expose exactly one tool, `next_recommended_task`, taking no
    arguments, returning a string.
  - The tool reads `fixture/PROGRESS-fixture.md` (resolve the path
    relative to THIS FILE, `Path(__file__).resolve().parent.parent /
    "fixture" / "PROGRESS-fixture.md"` -- never relative to the current
    working directory, since the server may be launched from anywhere)
    and scans it top to bottom for the first unchecked task line.

  Fixture format:
    `## <module-slug>` headings, each followed by task lines shaped
    `- [ ] <task-slug> -- <description>` (unchecked) or
    `- [x] <task-slug> -- <description>` (checked). A task line belongs
    to the most recent `## ` heading above it.

  Return value contract:
    On the first unchecked task found (top to bottom, module order
    preserved): return exactly
        f"{module_slug}/{task_slug} -- {description}"
    If every task is checked: return exactly "All tasks complete."

  Run it directly with `mcp.run()` under `if __name__ == "__main__"` so
  it speaks the stdio MCP transport when launched as a subprocess.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixture" / "PROGRESS-fixture.md"

mcp = FastMCP("progress-server")


@mcp.tool()
def next_recommended_task() -> str:
    """Return the first unchecked task in PROGRESS-fixture.md, top to
    bottom, formatted as '<module>/<task> -- <description>'."""
    raise NotImplementedError("parse FIXTURE_PATH and return the first unchecked task")


if __name__ == "__main__":
    mcp.run()
