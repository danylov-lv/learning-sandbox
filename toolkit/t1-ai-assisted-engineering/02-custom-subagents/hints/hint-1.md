A subagent is a Markdown file: YAML frontmatter, then a system prompt as
the body. Nothing more exotic than that. Before writing either agent,
think about what actually earns a subagent instead of just doing the work
inline in the main conversation: it's when the work would (a) generate a
lot of output you don't need to keep around afterward, or (b) benefit
from a narrower tool set than you'd want unrestricted in the main thread.

`description` is not documentation for a human -- it's the field the
model reads to decide, on its own, when to delegate to this agent. Write
it as a trigger condition ("use this when X"), not a summary of what the
agent does in the abstract.

For the code-reviewer's checklist specifically: think about the
difference between a checklist item and generic advice. "Check for bugs"
is not checkable -- two reviewers given the same diff wouldn't agree on
whether they did it. "Check that every new function has at least one
error path handled explicitly, not a bare except" is checkable.
