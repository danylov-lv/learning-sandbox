Don't start by writing prose about what a CLAUDE.md "should" contain in
the abstract. Start by actually using the sample-project the way a fresh
Claude Code session would have to: read `sample-project/README.md`, read
`sample-project/src/priceparser/__init__.py` end to end, and run its
tests yourself. Every fact you put in `CLAUDE.md` should trace back to
something you just verified is true of this project, not something you
assume is generically true of "a Python project."

Think about the actual failure mode project memory exists to prevent: a
fresh session (no memory of this conversation) opens this repo and has to
re-derive, from scratch, every piece of context you already have right
now. What would it get wrong first? What would it waste the most time
rediscovering? Those are your "Commands" and "What NOT to do" entries.

Separately, hold two different questions in your head while you write:
"what should live in memory" and "what should NOT." A file that tries to
capture everything true about a project rots the fastest, because half of
it stops being true within a week and nobody notices until it actively
misleads a session that trusted it.
