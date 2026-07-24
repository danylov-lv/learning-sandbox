No ready-made server code here -- just how to check your own
implementation before running the validator, and the exact parsing
regexes' shape if you want to sanity-check your own approach against it
(not to copy -- the validator's independent recomputation uses the same
idea, but you should write your own parsing loop, not reverse-engineer
this one).

A heading line looks like `## 02-sql-optimization` -- module name is
everything after `## ` with surrounding whitespace stripped. A task line
looks like `- [ ] 02-index-design -- choosing and validating indexes` --
note the exact spacing: `- [`, then a single space or `x`, then `] `,
then the slug, then ` -- `, then the description running to end of line.

To test your server manually without the validator's MCP client at all,
you can invoke Python's REPL-style smoke test:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'src')
from server import next_recommended_task
print(next_recommended_task())
"
```

Run from the task directory (`05-mcp-server/`). This calls your function
directly -- no MCP protocol involved -- so if this doesn't print the
right string, the protocol-level validator won't pass either, and
debugging here is much faster than debugging a subprocess handshake.

Once that's right, run `tests/validate.py` itself -- if it times out
rather than failing cleanly, check that `mcp.run()` is actually reached
(no exception before it, no accidentally missing `if __name__ ==
"__main__":` guard).
