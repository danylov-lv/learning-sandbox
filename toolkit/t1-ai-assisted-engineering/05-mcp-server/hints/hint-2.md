Parsing, concretely: read `fixture/PROGRESS-fixture.md` line by line. A line
starting with `## ` sets "current module" to whatever follows (strip
whitespace). A line starting with `- [ ] ` or `- [x] ` belongs to the
most recently seen module; split it into the checkbox state, the task
slug, and the description, using the ` -- ` separator between slug and
description. The first line you see with an empty checkbox (`[ ]`, not
`[x]`) is the one you return -- stop scanning there, don't keep looking
for more.

Format the return value EXACTLY as `f"{module}/{task_id} -- {description}"`
-- no extra whitespace, no trailing period, using the same ` -- ` (two
hyphens, spaces on both sides) the fixture itself uses. The validator
computes its own expected string the same way and compares for exact
equality.

Resolve the fixture path from `__file__`, not from `Path.cwd()` -- the
validator launches your server with `cwd` set to the task directory, but
you shouldn't rely on that; a server that only works when launched from
one specific directory isn't really portable, and `Path(__file__)`-based
resolution is the standard fix.

For the MCP wiring itself: `mcp = FastMCP("some-name")`, decorate your
function with `@mcp.tool()` directly above its `def`, and call
`mcp.run()` inside `if __name__ == "__main__":`. That's the entire
server -- FastMCP's default transport when run this way is stdio, which
is what the validator speaks to it over.
