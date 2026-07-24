# 01 -- Project Memory Done Right

## Backstory

You've been using Claude Code daily for a while, and you already know the
mechanics: drop a `CLAUDE.md` at a project root and Claude Code loads it
into every session automatically. What separates a `CLAUDE.md` that
actually pays for itself from one that quietly becomes noise isn't the
mechanic -- it's editorial judgment about what belongs in memory at all.

A memory file that tries to capture everything true about a project rots
fast: half of it stops being true within a sprint, and a session that
trusts a stale line wastes real time or does the wrong thing with
confidence. A memory file that only states the stable stuff -- build and
test commands, structural conventions the code actually enforces, the
shape of the codebase, the mistakes a newcomer predictably makes -- keeps
paying off for months. This task is about drawing that line on a project
small enough to see all of at once, before you draw it on something
bigger.

## What's given

- `sample-project/` -- a small, complete, correct library (`priceparser`):
  parses price strings like `"$1,234.56"` into `(cents, currency)` and
  formats them back. Read `sample-project/README.md` first, then the
  source at `sample-project/src/priceparser/__init__.py`. Its test suite
  (`sample-project/tests/test_priceparser.py`) passes right now -- you are
  not editing any of this, only writing memory about it.
- `deliverable/CLAUDE.md` -- an unfilled template with every required
  section already in place as a `[fill in ...]` placeholder.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked.
- `hints/` -- three levels of hints, none containing a ready-made
  CLAUDE.md.

## What's required

Fill in `deliverable/CLAUDE.md` -- all five sections:

1. **Commands** -- the real, verified command(s) to build/test this
   project.
2. **Conventions** -- the conventions this specific codebase actually
   follows, grounded in what you read.
3. **Architecture** -- what's where, and why.
4. **What NOT to do** -- concrete, plausible mistakes and the constraint
   that rules each one out.
5. **Memory vs rot** -- your own reflection on what belongs in a memory
   file like this one, and what you deliberately left out.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 01-project-memory/tests/validate.py
```

It checks, in order:

- All five required `## ` sections are present and long enough.
- No leftover `[fill in ...]` placeholder markers anywhere.
- Enough grounding vocabulary specific to `priceparser` appears in the
  file (function names, the money-as-cents convention, the currency
  handling) -- generic Python advice that could apply to any project
  won't clear this bar on its own.
- The file actually names `sample-project`'s real test invocation
  (something matching `pytest tests`), not a guessed or generic one.
- The "Memory vs rot" section uses real reflection vocabulary (rot,
  staleness, volatility, secrets, drift) -- not just a restatement of the
  other four sections.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Claude Code project memory: `CLAUDE.md` discovery and loading, and the
  `@path` import syntax for splitting memory across files
- What differentiates durable project knowledge from transient/volatile
  state worth keeping out of memory
- Editorial judgment in technical documentation: precision vs. coverage,
  and why an incomplete-but-accurate memory file beats an
  exhaustive-but-stale one
- Secrets and credentials hygiene: why they never belong in a file an AI
  session reads by default

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract across all six tasks -- spoilers, in general. Read it after
finishing this task, if at all.
