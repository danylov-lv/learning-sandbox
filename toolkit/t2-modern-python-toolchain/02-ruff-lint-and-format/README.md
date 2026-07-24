# 02 — Ruff Lint and Format

## Backstory

`reportkit` turns raw scrape rows into a summary report. It was written
fast, it "works", and nobody has ever run a linter on it. You've been
asked to bring it up to the team's standard before it grows: configure
ruff properly (not just turn it on) and clean up what it finds — for
real, not by muting every rule that complains.

## What's given

- `project/src/reportkit/report.py` — the report builder. Has several
  genuine lint violations and several genuine formatting violations
  (inconsistent quotes, cramped operators, missing blank lines).
- `project/src/reportkit/__init__.py` — re-exports `build_report` and
  `summarize` for `from reportkit import ...` callers. Ruff correctly
  flags these as unused imports (F401) — that's the intended, idiomatic
  re-export pattern, not a bug, and it's the reason this task requires a
  per-file exemption instead of a blanket one.
- `project/pyproject.toml` — has a `[tool.ruff]` table, but it's
  underspecified: only `line-length = 88` is set, nothing selects rule
  families beyond ruff's defaults, and there's no per-file exemption.
- `tests/validate.py` — the validator.
- `hints/` — three levels of hints.

## What's required

1. In `project/pyproject.toml`, configure ruff's lint settings under
   `[tool.ruff]` / `[tool.ruff.lint]`:
   - `line-length = 100`.
   - An explicit `select` list covering the default `E` and `F` families
     *plus* two rule families ruff does **not** enable by default:
     `I` (isort — import sorting) and `B` (flake8-bugbear — the mutable
     default argument on `summarize` is exactly what this catches).
   - A `per-file-ignores` entry that exempts `__init__.py`, and *only*
     `__init__.py`, from `F401`.
2. Fix `project/src/reportkit/report.py` so `ruff check` passes cleanly
   under that configuration — actually resolve each issue (remove the
   dead import, sort the import block, give `summarize` a real default,
   replace the bare `except`, fix the `== None` comparison, drop the
   placeholder-less f-string) rather than suppressing it with inline
   `# noqa` comments or widening `per-file-ignores`.
3. Run `ruff format` on the source so `ruff format --check` passes too.

Selecting `E` broadly (not just ruff's narrower default `E4/E7/E9`
subset) also pulls in `E501` (line-too-long) — which is exactly why the
`line-length` value you pick matters: one line in `report.py` is long
enough to violate the 88-character default but fits under 100.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t2-modern-python-toolchain
uv run python 02-ruff-lint-and-format/tests/validate.py
```

It checks, in order:

- `project/pyproject.toml` sets `line-length = 100`, selects `E`, `F`,
  `I`, and `B`, does not use `select=["ALL"]`/`ignore=["ALL"]`, and has a
  `per-file-ignores` entry that covers `__init__.py`'s `F401` and nothing
  else.
- `ruff check src` exits 0.
- `ruff format --check src` exits 0.
- Each planted issue is independently confirmed gone from
  `report.py`'s source (the stray import, the bare `except`, the mutable
  default, the `== None` comparison, the empty f-string) — checked by
  the validator itself, not inferred from ruff's exit code alone.
- `# noqa` usage under `src/` is capped at 0 — every fix must be real.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Ruff's rule selection model: `select`, `extend-select`, `ignore`, and
  why an explicit `select` list behaves differently from ruff's implicit
  defaults
- flake8-bugbear's `B006` and why a mutable default argument is a real
  bug, not a style nit
- isort's import-sorting convention (`I001`) and how ruff implements it
- `per-file-ignores` and the "re-export in `__init__.py`" pattern it
  exists for
- The difference between `ruff check` (lint) and `ruff format`
  (formatting) as separate subcommands with separate configuration

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
