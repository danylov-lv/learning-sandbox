No ready-made agent files here — just the exact shape the validator
checks, so you know what "done" looks like structurally.

**Frontmatter contract for both files:**

```
---
name: <exact string>
description: <non-empty, no leftover TODO/placeholder text>
tools: <comma-separated, e.g. Read, Bash, Grep -- optional but recommended>
model: <e.g. sonnet, haiku, or inherit -- optional>
---

<system prompt body, non-empty, no leftover TODO/placeholder text>
```

**`code-reviewer` specifically** needs at least 6 lines in its body that
start with `-` or `*` (a Markdown bullet), each one a concrete, checkable
item — not a placeholder. Count your own bullets before you consider it
done; the validator counts exactly this.

**`WHEN-NOT-TO-DELEGATE.md`** needs three `##` sections filled in with
real length and real vocabulary (context, overhead, delegate, tool,
subagent, scope, checklist show up naturally if you're actually
answering the question rather than padding it) — `## When to delegate`,
`## When NOT to delegate`, `## Failure modes observed`.

For "Failure modes observed": you don't need to have literally run these
agents through Claude Code to write this section honestly — reasoning
concretely through a specific scenario for each agent (what input would
make its checklist or its scoping fail) is a legitimate way to fill this
in, as long as it's specific to the agents you actually wrote, not
generic subagent-design commentary.
