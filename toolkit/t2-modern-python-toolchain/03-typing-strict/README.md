# 03 — Typing, Strict

## Backstory

`normkit` cleans up messy scraped fields — raw price strings, optional
tags, currency codes — before they hit the database. It was written
without type hints, "because it's obvious what it does." It is not
obvious: it currently has a real bug (`to_currency_code` silently returns
`None` on bad input instead of raising) and a latent one
(`parse_optional_tag` crashes on the exact input its name promises to
handle). Both are exactly the kind of bug `mypy --strict` catches before
it ships. Your job: turn strict mode on and make it pass — by fixing the
code, not by placating the checker.

## What's given

- `project/src/normkit/normalize.py` — four functions, each with a
  genuine typing problem: two are missing annotations entirely, one
  mistypes an optional parameter (and mishandles it at runtime), one
  claims to return `str` but returns `None` on one path.
- `project/tests/test_normalize.py` — a small given pytest suite that
  pins the *correct* behavior, including the two cases the current bugs
  get wrong. You will not edit this file.
- `project/pyproject.toml` — has a `[tool.mypy]` table with
  `python_version` and `mypy_path` already set, but no `strict` flag.
- `tests/validate.py` — the validator.
- `hints/` — three levels of hints.

## What's required

1. In `project/pyproject.toml`, set `[tool.mypy].strict = true`.
2. Fix `project/src/normkit/normalize.py` so `mypy` passes cleanly under
   strict mode **and** `project/tests/test_normalize.py` still passes
   unmodified. In particular:
   - Add real parameter and return annotations where they're missing.
   - Give `parse_optional_tag` a type that matches what it actually
     accepts, and make it behave correctly for that input instead of
     crashing.
   - Make `to_currency_code` either return a `str` on every path or
     raise — not silently return `None` from a function typed `-> str`.
   Read the given test file to see exactly what behavior is expected;
   it's the contract you're implementing against, not just decoration.
3. Do not add `# type: ignore` anywhere — every issue here is cleanly
   fixable without one, and the validator caps it at zero.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t2-modern-python-toolchain
uv run python 03-typing-strict/tests/validate.py
```

It checks, in order:

- `project/pyproject.toml`'s `[tool.mypy]` has `strict = true`.
- `mypy src` (run from `project/`, picking up that config) exits 0.
- `pytest -q` still passes against the given, unedited test suite.
- `# type: ignore` usage under `src/` is capped at 0.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- What `mypy --strict` actually enables (`disallow_untyped_defs`,
  `disallow_any_generics`, `no_implicit_optional`, and friends) versus
  mypy's lenient default mode
- PEP 484's implicit-Optional rule and why `param: str = None` is not the
  same as `param: str | None = None`
- Why a function's declared return type is a promise to its callers, and
  what "return `None`" from a `-> str` function actually breaks downstream
- The difference between silencing a type error and fixing the bug it's
  pointing at

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
