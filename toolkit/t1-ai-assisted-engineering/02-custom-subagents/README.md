# 02 -- Custom Subagents

## Backstory

Repeated test-running and review requests need clear scopes and reports. Define two reusable Codex agents, then explain when the context and coordination overhead outweighs delegation. Instructions to avoid edits express intent; agents inherit the parent session's permissions.

## What's given

Unsolved TOML templates in `deliverable/.codex/agents/`, a `WHEN-NOT-TO-DELEGATE.md` template, three hints, and a structural validator.

## What's required

Fill `test-runner.toml` and `code-reviewer.toml`. Each needs non-placeholder `name`, `description`, and `developer_instructions` strings. Names must be exactly `test-runner` and `code-reviewer`, with no duplicates. The reviewer instructions must include at least six concrete checklist bullets. Define scope, stopping conditions, and evidence to report. Fill the three sections in `WHEN-NOT-TO-DELEGATE.md`.

For this task the supported fields are name, description, developer_instructions, model, and model_reasoning_effort. Optional model settings must be non-empty strings; omit them to inherit rather than writing `inherit`. The validator rejects fields outside this task subset. Model availability is not validated locally.

Keep these exercise artifacts in `deliverable/`. For an optional live trial, copy them into `.codex/agents/` in a temporary project and explicitly request delegation there. Do not change the sandbox's active agent configuration.

## Completion criteria

From the module root run `uv run python 02-custom-subagents/tests/validate.py`.

The validator parses TOML, checks fields, unique names and the review checklist, then applies the existing document gate to the delegation reflection. It does not spawn agents or prove instruction compliance.

## Estimated evenings

1

## Topics to read up on

- Project-scoped agent files and developer_instructions
- Inherited permissions versus instructions to avoid edits
- Delegation overhead, context transfer, and evidence-based reports
- Choosing when to explicitly request a subagent

Reference: https://learn.chatgpt.com/docs/agent-configuration/subagents

## Off-limits

The module's `.authoring/` directory contains authoring and grading notes. Do not consult spoilers before attempting the tasks.
