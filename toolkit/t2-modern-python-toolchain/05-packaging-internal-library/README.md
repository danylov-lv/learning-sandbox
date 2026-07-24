# 05 — Packaging an Internal Library

## Backstory

`pricelib` is a small internal helper — a `summarize()` function and a
CLI that prints a quick report — that a few of your team's other tools
want to depend on. Right now it's just a folder someone copies around.
Your job: make it a real, buildable, installable package with a proper
`src` layout, so it can be built once (`uv build`) and installed anywhere
(`pip install pricelib-0.4.0-py3-none-any.whl`) without dragging its
source tree along.

## What's given

- `project/src/pricelib/__init__.py` — the library: `summarize()` and a
  `__version__` string. Given, not edited.
- `project/src/pricelib/cli.py` — the console entry point. Prints one
  line combining the package version and a summary of a fixed sample.
  Given, not edited.
- `project/pyproject.toml` — **broken**: no `[build-system]`, no
  `[project].version`, no `[project.scripts]`. `uv build` cannot produce
  anything from it as-is.
- `tests/validate.py` — the validator.
- `hints/` — three levels of hints.

## What's required

Fix `project/pyproject.toml` only:

1. Add a real `[build-system]` — either `hatchling` or uv's own
   `uv_build` backend.
2. Add `[project].version`, and make it match the `__version__` string
   already in `src/pricelib/__init__.py` exactly — the package's version
   metadata and its own `__version__` attribute must agree.
3. Add a `[project.scripts]` entry point named exactly `pricelib`,
   pointing at `pricelib.cli:main`.
4. Keep the `src` layout intact — the package lives at
   `project/src/pricelib/`. Do not create a `project/pricelib/` directory
   at the project root; a stray flat-layout copy defeats the entire
   point of `src/` (it's what stops `import pricelib` from silently
   working out of an unbuilt checkout).

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t2-modern-python-toolchain
uv run python 05-packaging-internal-library/tests/validate.py
```

It checks, in order:

- `project/src/pricelib/` exists and no stray `project/pricelib/` sits
  next to it.
- `project/pyproject.toml` has a valid `[build-system]`, a
  `[project].version` matching `__version__`, and the `pricelib` console
  script mapped correctly.
- `uv build` succeeds and produces both a wheel and an sdist under
  `project/dist/`.
- The wheel installs cleanly into a throwaway venv, and the *installed*
  `pricelib` command (not `uv run` inside the source tree — the actual
  installed script) prints the expected version and summary line.
- The throwaway venv and `project/dist/` are removed afterward either
  way.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- The `src` layout vs the flat layout, and the accidental-import bug the
  `src` layout specifically prevents
- Build backends (`hatchling`, `uv_build`) and what
  `[build-system].build-backend` actually does at build time
- Wheels vs sdists — what each contains and when each gets used
- Keeping a single source of truth for a package's version (a
  `__version__` string vs a build backend's dynamic-version support)
- `uv build`, and installing a built wheel into an unrelated venv with
  `uv pip install`

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
