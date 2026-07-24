# Toolkit / t1 -- AI-Assisted Engineering

Six single-evening tasks about using Claude Code well, at a working
level beyond "what is a prompt." Every task references a real,
currently-existing Claude Code mechanism (project memory, subagents,
hooks, headless mode, MCP) -- nothing invented for the exercise. There is
no capstone; the tasks are independent and can be done in any order,
though task 01 is worth doing first since a good `CLAUDE.md` improves
every other sandbox task you touch afterward.

This module is pure Python with no services -- no `docker-compose.yml`,
no host ports (unlike most of the other sandbox modules, see
`CONVENTIONS.md`'s ports table).

## Tasks

1. **`01-project-memory`** -- write a proper `CLAUDE.md` for a given toy
   project. What belongs in memory vs. what rots.
2. **`02-custom-subagents`** -- author a test-runner and a code-reviewer
   subagent, plus when NOT to delegate to either.
3. **`03-hooks-and-guardrails`** -- a `PostToolUse` hook that runs tests
   after every edit, and one that runs `ruff check`, both behaviorally
   graded against real pass/fail fixtures.
4. **`04-headless-and-ci`** -- `claude -p` in a headless review script,
   plus a label-triggered (not push-triggered) GitHub Actions AI review
   step.
5. **`05-mcp-server`** -- a tiny stdio MCP server exposing sandbox
   progress, graded by actually speaking the MCP protocol to it.
6. **`06-verification-discipline`** -- review four plausible-but-mostly-
   flawed patches, write verdicts and tests that genuinely catch the
   planted bugs. The core skill of AI-assisted work.

## Running a task's validator

Every task follows the same pattern, from this directory:

```bash
cd toolkit/t1-ai-assisted-engineering
uv sync   # once, to install this module's dependencies
uv run python <NN-task-name>/tests/validate.py
```

Each prints `PASSED` or `NOT PASSED: <reason>` and exits 0/1
accordingly. Read each task's own README.md for what exactly it checks.

## Shared harness

`harness/common.py` -- pass/fail plumbing (`guarded`, `not_passed`,
`passed`), a Markdown doc-gate (required sections, placeholder
detection, grounding keywords, quantitative-claim checks, hostile-
answer-quality checks) used by tasks 01, 02, and 06, a YAML frontmatter
parser used by task 02, and subprocess grading helpers (`run_pytest`,
`run_hook`) used by tasks 03 and 06. Copied from and consistent with
`17-system-design/harness/common.py`'s conventions, extended for this
module's behavioral (subprocess-driven) tasks.

## Off-limits

`.authoring/` documents this module's grading contract and (for task 06
specifically) planted-bug ground truth -- spoilers. Read it after
finishing the relevant task, not before. Reading `.authoring/design.md`
before attempting task 06 defeats that task's entire point.
