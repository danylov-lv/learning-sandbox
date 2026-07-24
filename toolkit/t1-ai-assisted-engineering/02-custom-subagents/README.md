# 02 -- Custom Subagents

## Backstory

You already delegate to Claude Code's built-in subagents (Explore, Plan,
general-purpose) without thinking about it. The next step is writing your
own: a subagent is just a Markdown file with YAML frontmatter under
`.claude/agents/`, and the moment you have a task you keep re-explaining
the same way ("run this module's tests and tell me pass/fail," "review
this diff against my checklist"), that's a signal to write the
instructions once as a subagent instead of repeating them every session.

The skill this task actually tests isn't the file format -- that's
five minutes of documentation. It's judgment: what makes a `description`
good enough that Claude reliably picks the right agent for the right
task, what tool restrictions actually matter for a given agent's job, and
-- just as important -- when delegating is the wrong call in the first
place.

## What's given

- `deliverable/.claude/agents/test-runner.md` -- unfilled stub.
- `deliverable/.claude/agents/code-reviewer.md` -- unfilled stub,
  including a checklist skeleton.
- `deliverable/WHEN-NOT-TO-DELEGATE.md` -- unfilled template.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked.
- `hints/` -- three levels of hints.

## What's required

1. Fill in `test-runner.md`: a subagent that runs a module's test/
   validator suite and reports pass/fail concisely.
2. Fill in `code-reviewer.md`: a subagent that reviews a diff against an
   explicit checklist (at least 6 concrete, checkable bullet items) baked
   into its system prompt.
3. Fill in `WHEN-NOT-TO-DELEGATE.md`: when to delegate to each agent,
   when NOT to, and failure modes you'd expect or observed.

You may add a third agent under `.claude/agents/` if you want to, but it
is not required and not graded.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 02-custom-subagents/tests/validate.py
```

It checks, in order:

- At least 2 agent `.md` files exist under `deliverable/.claude/agents/`,
  each with valid YAML frontmatter (`name` and `description` required;
  `tools` and `model`, if present, well-formed) and a non-empty system
  prompt body.
- Among them, one has frontmatter `name: test-runner` and one has
  `name: code-reviewer` (exact match).
- `code-reviewer`'s system prompt body contains at least 6 non-placeholder
  bulleted checklist items.
- `WHEN-NOT-TO-DELEGATE.md`'s three required sections are present, long
  enough, free of placeholders, and use real grounding vocabulary.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Claude Code subagents: the `.claude/agents/<name>.md` file format,
  frontmatter fields (`name`, `description`, `tools`, `model`), and how
  Claude decides when to delegate based on `description`
- Context window isolation: why running work in a subagent keeps its
  output out of the main conversation, and what that costs (a fresh
  context with no memory of the conversation so far, a round trip)
- Tool restriction as a design choice for an agent's job, not just a
  security afterthought
- Prompt writing for a checklist-driven review agent vs. a free-form one

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract across all six tasks -- spoilers, in general. Read it after
finishing this task, if at all.
