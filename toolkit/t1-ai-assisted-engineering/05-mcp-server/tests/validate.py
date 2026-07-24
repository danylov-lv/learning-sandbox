"""Validator for 05-mcp-server. Run from the module root:

    cd toolkit/t1-ai-assisted-engineering
    uv run python 05-mcp-server/tests/validate.py

Fully behavioral: spawns the learner's src/server.py as a real subprocess
and speaks the MCP stdio protocol against it via the official `mcp`
Python SDK client (initialize -> tools/list -> tools/call), with a hard
timeout so a hung or non-responding server fails cleanly instead of
hanging the validator forever.

The expected answer is computed independently from the same fixture file
the server reads, using the same parsing rule documented in
src/server.py's docstring -- never by importing the learner's module.

Implementation note: every "expected failure" condition below (missing
tool, tool error, empty result, mismatch) is reported by RETURNING a
result dict from the async code, never by raising/exiting from inside it.
`ClientSession`/`stdio_client` run their own internal task groups, and
Python 3.11+ task groups wrap ANY exception that escapes their `async
with` body in an ExceptionGroup/BaseExceptionGroup -- including a
deliberate SystemExit from `not_passed()`. Raising there produces two
garbled NOT PASSED-shaped lines instead of one clean one. Only truly
unexpected failures (the subprocess never starting, the protocol hanging)
are handled via a single try/except wrapped around `asyncio.run(...)` in
`main()`, outside any task group.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

SERVER_PATH = TASK_DIR / "src" / "server.py"
FIXTURE_PATH = TASK_DIR / "fixture" / "PROGRESS-fixture.md"
TOOL_NAME = "next_recommended_task"
TIMEOUT_SECONDS = 20

_HEADING_RE = re.compile(r"^##\s+(\S+)\s*$")
_TASK_RE = re.compile(r"^-\s\[( |x)\]\s+(\S+)\s*--\s*(.+?)\s*$")


def _expected_next_task() -> str:
    if not FIXTURE_PATH.exists():
        not_passed(f"fixture not found: {FIXTURE_PATH}")
    module = None
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        h = _HEADING_RE.match(line)
        if h:
            module = h.group(1)
            continue
        t = _TASK_RE.match(line)
        if t and module is not None:
            checked, task_id, description = t.groups()
            if checked == " ":
                return f"{module}/{task_id} -- {description}"
    return "All tasks complete."


async def _run_protocol() -> dict:
    """Returns {"ok": True, "actual": str} or {"ok": False, "reason": str}.
    Never raises for an "expected" grading failure -- see module docstring."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        cwd=str(TASK_DIR),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            if TOOL_NAME not in tool_names:
                return {"ok": False, "reason": f"tools/list did not include '{TOOL_NAME}' (found: {tool_names})"}

            call_result = await session.call_tool(TOOL_NAME, arguments={})

            if getattr(call_result, "isError", False):
                text = "".join(
                    getattr(block, "text", str(block)) for block in (call_result.content or [])
                )
                return {"ok": False, "reason": f"tools/call for '{TOOL_NAME}' returned an error: {text[:300]}"}

            texts = [getattr(block, "text", None) for block in (call_result.content or [])]
            texts = [t for t in texts if t is not None]
            if not texts:
                return {"ok": False, "reason": f"tools/call for '{TOOL_NAME}' returned no text content"}

            return {"ok": True, "actual": texts[0].strip()}


@guarded
def main() -> None:
    if not SERVER_PATH.exists():
        not_passed(f"server not found: {SERVER_PATH}")

    expected = _expected_next_task()

    try:
        result = asyncio.run(asyncio.wait_for(_run_protocol(), timeout=TIMEOUT_SECONDS))
    except (asyncio.TimeoutError, TimeoutError):
        not_passed(f"server did not respond within {TIMEOUT_SECONDS}s (initialize/list_tools/call_tool)")
    except BaseExceptionGroup as eg:  # noqa: F821 - Python 3.11+
        leaves = eg.exceptions
        msg = "; ".join(f"{type(e).__name__}: {e}" for e in leaves[:3])
        not_passed(f"MCP protocol exchange with server failed: {msg}")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        not_passed(f"MCP protocol exchange with server failed: {type(e).__name__}: {e}")

    if not result["ok"]:
        not_passed(result["reason"])

    actual = result["actual"]
    if actual != expected:
        not_passed(f"next_recommended_task() returned {actual!r}, expected {expected!r}")

    passed(f"MCP handshake + tools/call OK, next task = {actual!r}")


if __name__ == "__main__":
    main()
