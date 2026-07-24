MCP demystifies fastest by building the smallest possible server and
watching it actually speak the protocol, rather than reading the spec
end to end first. `FastMCP` (from `mcp.server.fastmcp`) hides the
JSON-RPC framing for you -- you write a plain Python function, decorate
it with `@mcp.tool()`, and the decorator handles turning it into
something `tools/list` and `tools/call` can see.

Read the docstring already in `src/server.py` closely -- it pins down
the exact fixture format and the exact return-value format the validator
checks. This task rewards precision more than cleverness: the parsing
logic itself is a small, standard "scan lines, track current heading"
loop you've written before in other tasks.

Before worrying about the validator at all, get the tool function itself
right and testable as plain Python: write a small `if __name__ ==
"__main__"` scratch check (not committed, just for yourself) that calls
`next_recommended_task()` directly and prints the result, without
involving MCP at all. Once that's right, the MCP wiring around it is
almost mechanical.
