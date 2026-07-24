# t2 — Modern Python Toolchain

## What this module covers

Five single-evening tasks that modernize a Python workflow around one
tool family: **uv** for both project and tool management, **ruff** for
lint and format, **mypy** in strict mode, **pre-commit** to wire it all
together automatically, and packaging a small internal library with a
proper `src` layout. Each task ships a genuinely broken or absent config
(or genuinely broken code) — you fix it, and a validator runs the real
tool against your fix and checks the result, exactly the way CI would.

No docker-compose, no database — this module is pure tooling.

## Stack

- **uv** — project sync/run/lock and tool management (`uv tool run` /
  `uvx`), exercised directly in tasks 01 and 05.
- **ruff** — lint (`ruff check`) and format (`ruff format`), task 02.
- **mypy** — `--strict` type checking, task 03 (and wired into
  pre-commit for task 04).
- **pre-commit** — hook orchestration, task 04.
- All four are pinned in this module's own `[dependency-groups].dev`
  (see `pyproject.toml`) so the *validators* run a known version — each
  task's own `project/` may be a separate, independent uv project with
  its own (gitignored) `uv.lock`, generated when you run `uv sync` or
  `uv build` inside it.

## Getting started

```bash
cd toolkit/t2-modern-python-toolchain
uv sync
```

Then, per task, fix the given broken state and run its validator from
the module root:

```bash
uv run python 01-uv-project-management/tests/validate.py
```

A validator prints exactly one line and exits: `PASSED` on success, or
`NOT PASSED: <reason>` naming the first thing that's still wrong. No raw
tracebacks leak to you.

## Tasks

| # | Task | What's broken in the starting state |
|---|------|---------------------------------------|
| 01 | uv-project-management | `project/pyproject.toml` has no runtime dependency, no console entry point, no dev dependency group |
| 02 | ruff-lint-and-format | `project/pyproject.toml`'s `[tool.ruff]` is underspecified; the source has real lint and format violations |
| 03 | typing-strict | `project/pyproject.toml`'s `[tool.mypy]` has no `strict` flag; the source has real typing bugs (one of them a live runtime bug) |
| 04 | pre-commit-wiring | `.pre-commit-config.yaml` does not exist yet — it's the deliverable |
| 05 | packaging-internal-library | `project/pyproject.toml` has no `[build-system]`, no version, no console entry point |

- **01** — fix a CLI's `pyproject.toml` so `uv sync` installs correctly,
  `uv run pricetool` produces the right output, `uv run pytest` picks up
  the dev group, and `uv tool run --from . pricetool` (the explicit form
  of `uvx`) works the same way — the project-management path and the
  tool-management path, against the same entry point.
- **02** — configure ruff's `select` (defaults plus two non-default rule
  families), `line-length`, and a scoped `per-file-ignores`, then
  actually fix every planted lint and format violation — no blanket
  `ignore=["ALL"]`, no stray `# noqa`.
- **03** — turn on `mypy --strict` and fix four real typing problems,
  including one that's also a live runtime bug a given, unedited pytest
  suite catches.
- **04** — write `.pre-commit-config.yaml` from scratch, wiring ruff
  (lint + format), strict mypy, and two basic hygiene hooks; validated
  against a clean fixture (must pass) and a bad fixture (must fail) in
  throwaway git repos.
- **05** — fix a library's `pyproject.toml` (build-system, version,
  console script) so `uv build` produces a wheel and sdist, and the
  *installed* wheel's console script runs correctly from a throwaway
  venv — proving the `src` layout and packaging metadata are both right,
  not just that the source imports.

## Verification philosophy

- **Behavioral, not cosmetic.** Every task shells out to the real tool
  (`uv`, `ruff`, `mypy`, `pre-commit`) and checks its actual exit code
  and output, the same way a CI pipeline would — never a string match on
  the learner's config alone.
- **Structural checks close the loopholes.** Where a tool's exit code
  alone could be gamed (disabling every rule, ignoring the whole file,
  silencing every warning), the validator also parses the learner's own
  config and independently confirms specific planted issues are gone
  from the source — and caps escape hatches like `# noqa` and
  `# type: ignore` at a small bound.
- **Given code stays given.** Where a task is about configuration (01,
  02's fixture shape, 05), the source the CLI/library runs is already
  correct and unedited — you're proven right or wrong entirely by the
  config you write. Where a task is about the code itself (02's
  violations, 03's typing bugs), a small given, unedited pytest suite
  pins the behavior that must survive your fix.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents this module's grading contract and the
planted-issue ground truth per task — read it after finishing a task, if
at all, same rule as every other module in this repo.
