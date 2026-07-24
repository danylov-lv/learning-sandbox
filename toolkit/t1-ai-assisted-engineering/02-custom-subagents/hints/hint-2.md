Frontmatter fields, concretely:

- `name` must be the exact string the validator looks for
  (`test-runner`, `code-reviewer`) -- this mirrors the real convention
  where the filename and the `name:` field are how Claude Code and you
  both refer to the agent, so keep them matched.
- `tools`, if you set it, restricts what the agent can call — a
  comma-separated list of tool names (`Read, Grep, Bash`). Leaving it out
  means the agent inherits the parent's tool access; for a review agent
  that should never write files, an explicit restricted list is the
  actual point of setting it at all.
- `model` lets you route cheap, mechanical work (like running a fixed
  test command) to a smaller/faster model than what you're using for
  the main conversation.

For the `test-runner` system prompt: it should tell the agent HOW to find
the right command to run, not hardcode one specific command — this repo
has a different `uv run ...` invocation per task, documented in each
task's own README under "Completion criteria". Have the agent read that
section rather than guessing, and report back using this repo's own
`PASSED` / `NOT PASSED: <reason>` convention so its report is legible
without translation.

For `WHEN-NOT-TO-DELEGATE.md`: "when NOT to" is not the inverse of "when
to" restated negatively — think about the actual cost of delegating
(a fresh context window, a round trip, loss of the main conversation's
accumulated context) and name situations where that cost isn't worth
paying, or where the agent's tool restrictions would actively get in its
way.
