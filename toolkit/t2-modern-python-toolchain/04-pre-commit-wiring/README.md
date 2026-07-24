# 04 — pre-commit Wiring

## Backstory

Tasks 02 and 03 taught you to run ruff and mypy by hand. That doesn't
scale to a team — someone will forget, every time. Wire both into
`pre-commit` alongside a couple of basic hygiene hooks, so a bad commit
gets caught before it lands, not in code review three days later.

## What's given

- `fixtures/clean/statkit/` — a tiny, already-correct package
  (`mean`/`variance`). Fully typed, ruff-clean, no whitespace or
  newline issues. Your hooks must pass on this with **zero** changes
  needed.
- `fixtures/bad/statkit/` — the same package with several real problems
  planted at once: an unused import, a function missing type
  annotations, a line with trailing whitespace, and a file missing its
  final newline. Your hooks must **fail** on this.
- `tests/validate.py` — the validator. It stages each fixture into its
  own throwaway git repo under `scratch/` (removed afterward) and runs
  `pre-commit run --all-files` against it.
- `hints/` — three levels of hints.

There is **no starting `.pre-commit-config.yaml`** — writing it from
scratch is the deliverable.

## What's required

Create `.pre-commit-config.yaml` in this task directory (a sibling of
`README.md`, not inside `fixtures/`), wiring five hooks across three
repos:

1. **ruff** — the lint hook (`id: ruff`) and the format hook
   (`id: ruff-format`), from the `astral-sh/ruff-pre-commit` repo.
2. **mypy** — from the `pre-commit/mirrors-mypy` repo, run with
   `--strict` (pass it via the hook's `args`).
3. **Two basic hygiene hooks** from `pre-commit/pre-commit-hooks`:
   `trailing-whitespace` and `end-of-file-fixer`.

Pin a `rev:` for every repo (a tag, not a branch) — that's what makes a
pre-commit config reproducible across machines.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t2-modern-python-toolchain
uv run python 04-pre-commit-wiring/tests/validate.py
```

It checks, in order:

- `.pre-commit-config.yaml` exists and structurally wires all five
  required hook ids, with `--strict` in the mypy hook's `args`.
- In a throwaway git repo, `pre-commit run --all-files` against the
  **clean** fixture passes with no modifications needed.
- In a second throwaway git repo, the same command against the **bad**
  fixture fails — proving the hooks actually catch a real problem, not
  just that the YAML parses.
- The throwaway `scratch/` directory is removed either way.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly. The
first `pre-commit run` for a fresh hook environment downloads and builds
it — expect the first run to take a minute or two, and subsequent runs
to be fast (pre-commit caches environments in `~/.cache/pre-commit`,
keyed by repo and rev, not by which directory ran them).

## Estimated evenings

1

## Topics to read up on

- pre-commit's config schema: `repos`, `rev`, `hooks`, `id`, `args`
- Why hook revisions should be pinned to a tag, not `main`/`master`
- The difference between `pre-commit run --all-files` (what CI runs) and
  the installed git hook that only sees staged/changed files
- `ruff-pre-commit`'s two hook ids (`ruff` for lint, `ruff-format` for
  formatting) and why they're separate hooks
- How pre-commit's hook environments are cached and invalidated

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
