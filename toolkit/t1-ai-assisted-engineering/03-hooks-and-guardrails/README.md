# 03 -- Hooks and Guardrails

## Backstory

Project memory (task 01) and a well-scoped subagent (task 02) both rely
on Claude choosing to do the right thing. A hook doesn't ask -- it's a
shell command Claude Code runs automatically at a fixed point in the
tool-use lifecycle (before or after a tool call, at session start/stop,
etc.), and it can feed structured feedback straight back into the
conversation. That's the difference between "the memory file says to run
the tests" and "the tests actually ran, and Claude was told the result,"
which matters the moment you're moving fast enough to forget the first
one yourself.

This task builds two real guardrails: one that runs this project's tests
after every edit and reports failures back to Claude, and one that runs
`ruff check` the same way. Both use the same mechanism
(`PostToolUse`, matched on `Edit`/`Write`), so the second is mostly about
proving you understood the first, not learning something new.

## What's given

- `deliverable/.claude/settings.json` -- wires two `PostToolUse` hook
  entries to two scripts. The wiring is already correct; you are not
  editing this file's structure, only the two scripts it points at (you
  may still open it to see exactly how a hook entry is shaped).
- `deliverable/.claude/hooks/run-tests.py` -- stub, `raise
  NotImplementedError`.
- `deliverable/.claude/hooks/lint.py` -- stub, `raise NotImplementedError`.
- `tests/fixtures/` -- four tiny fixture projects the validator uses to
  behaviorally exercise your scripts: `tests-passing/`, `tests-failing/`
  (for `run-tests.py`), `lint-clean/`, `lint-dirty/` (for `lint.py`).
  Read them; they're small.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked and how it invokes your scripts.
- `hints/` -- three levels of hints, including the exact command to test
  a hook script by hand before running the validator.

## What's required

Implement both hook scripts under `deliverable/.claude/hooks/`, each
following the contract documented in its own docstring:

1. **`run-tests.py`** -- read the JSON payload Claude Code sends on
   stdin, run the project's test suite (`sys.executable -m pytest`,
   never a bare `python`), and report success/failure back.
2. **`lint.py`** -- same shape, but runs `ruff check` instead of pytest.

Both must exit `0` on success with no block signal, and on failure either
exit non-zero or print `{"decision": "block", "reason": "..."}` JSON to
stdout.

Do not change `deliverable/.claude/settings.json`'s structure or the
required filenames (`run-tests.py`, `lint.py`) -- the validator locates
your scripts by matching those exact filenames referenced from the
hook commands.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 03-hooks-and-guardrails/tests/validate.py
```

It checks, in order:

- `settings.json` has at least 2 `PostToolUse` entries, one referencing
  `run-tests.py` and one referencing `lint.py`, each with a `matcher`
  that actually matches both the strings `"Edit"` and `"Write"` (tested
  as a real regex, not by substring).
- `run-tests.py`, invoked as a real subprocess against the
  `tests-passing` fixture, exits 0 with no block signal.
- `run-tests.py`, invoked against `tests-failing`, signals failure
  (non-zero exit or `decision: block` JSON).
- `lint.py`, invoked against `lint-clean`, exits 0 with no block signal.
- `lint.py`, invoked against `lint-dirty`, signals failure.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Claude Code hooks: the `PreToolUse` / `PostToolUse` lifecycle, the
  `matcher` field as a regex against the tool name, and the difference
  between what each event can and cannot prevent
- The hook stdin JSON schema and the two ways a hook communicates a
  result back (process exit code vs. structured JSON on stdout)
- Why `PostToolUse` cannot undo a completed `Edit`/`Write`, and what
  `{"decision": "block", ...}` actually does instead
- Subprocess invocation pitfalls on Windows: PATH resolution ambiguity
  for a bare interpreter name vs. `sys.executable`
- `ruff check`'s exit code convention and how it differs from `ruff
  format --check`

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract across all six tasks -- spoilers, in general. Read it after
finishing this task, if at all.
