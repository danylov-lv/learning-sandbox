# Verification scope: toolkit/t1-ai-assisted-engineering

## Local checks

- The module dependency lock and authoring-contract CI pass.
- The six unsolved task validators exit 1 with NOT PASSED. Task 05 can also emit MCP server diagnostics on stderr.
- Agent and workflow validators accept valid synthetic artifacts and reject malformed fields, placeholders, duplicate names, unsuitable triggers, misplaced label conditions, and conflicting sandbox flags.
- Hook checks distinguish valid feedback from crashes, exercise Codex payloads, and accept the documented feedback forms. Full behavioral checks cover all four pytest/ruff fixtures.
- Ruff passes for the updated validators. Learner completion checkboxes and task 06 patch code remain intact.

## Integration coverage

Local parsing and subprocess checks do not certify authenticated model execution, live agent selection, hook dispatch in a Codex session, Codex MCP client configuration, or hosted GitHub Actions. These integrations need isolated live trials when exercised. No exercise configuration is installed at the sandbox root.

## References

- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/hooks
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/github-action
- https://developers.openai.com/codex/mcp
