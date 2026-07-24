# 05 -- A Minimal MCP Server

## Backstory

You connect MCP servers other people wrote all the time; this task
demystifies the mechanism by building one yourself. MCP is not magic --
it's a small JSON-RPC protocol over stdio (for a local server) with a
handshake (`initialize`), a discovery call (`tools/list`), and an
invocation call (`tools/call`). Once you've written the smallest possible
server that answers all three correctly, every third-party MCP server
you connect afterward is instantly less mysterious.

The tool you're building is genuinely useful for this repo: a server
that reads a progress checklist and answers "what should I work on
next?" -- the kind of small, self-contained, read-only tool MCP is
actually good for.

## What's given

- `src/server.py` -- stub. Docstring pins down the exact fixture format
  and exact return-value contract; the tool function itself
  `raise NotImplementedError`.
- `fixture/PROGRESS-fixture.md` -- a small, fixed fixture shaped like this
  repo's real PROGRESS.md, so grading is fully deterministic and never
  depends on the repo's actual, ever-changing progress. Do not edit it.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly how it speaks MCP to your server.
- `hints/` -- three levels of hints, including a way to smoke-test your
  parsing logic directly, without MCP in the loop at all.

## What's required

Implement `next_recommended_task()` in `src/server.py`: a zero-argument
MCP tool that reads `fixture/PROGRESS-fixture.md` and returns the first
unchecked (`- [ ]`) task, top to bottom, formatted exactly as
`"<module>/<task> -- <description>"` (or `"All tasks complete."` if none
are unchecked). Wire it up with `FastMCP` and run it over stdio.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 05-mcp-server/tests/validate.py
```

This is fully behavioral: the validator spawns `src/server.py` as a real
subprocess and speaks the actual MCP stdio protocol against it
(`initialize` -> `notifications/initialized` -> `tools/list` ->
`tools/call`) via the official `mcp` Python SDK client, with a 20-second
timeout. It checks:

- The server responds to the handshake and lists a tool named
  `next_recommended_task`.
- Calling that tool returns the correct next task, computed
  independently by the validator from the same fixture file.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly. A
hung or non-responding server fails cleanly after the timeout rather
than hanging the validator.

## Estimated evenings

1

## Topics to read up on

- MCP fundamentals: the stdio transport, the JSON-RPC message shape, and
  the `initialize` / `tools/list` / `tools/call` request lifecycle
- The Python `mcp` SDK's `FastMCP` high-level server API vs. the
  low-level server API it wraps
- MCP client basics: `StdioServerParameters`, `stdio_client`, and
  `ClientSession` from `mcp.client.stdio` / `mcp`
- Resolving a data file path relative to a script's own location
  (`Path(__file__)`) vs. relative to the process's current working
  directory, and why a long-running server should prefer the former

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract across all six tasks -- spoilers, in general. Read it after
finishing this task, if at all.
