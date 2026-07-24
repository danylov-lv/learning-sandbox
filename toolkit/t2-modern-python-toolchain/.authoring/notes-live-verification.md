# Live verification notes — t2-modern-python-toolchain

Off-limits to the learner until after they finish a task. Records the
exact live verification performed during authoring: tool versions
present, and for each task, the stock-fails / reference-passes /
reverted-to-stock sequence actually run.

## Environment at authoring time

```
uv 0.10.9 (f675560f3 2026-03-06)
ruff 0.15.7            (global; module dev-group pinned ruff>=0.15 resolved to 0.16.0)
mypy 1.7.1 (compiled)  (global; module dev-group pinned mypy>=1.7 resolved to 2.3.0)
pyright 1.1.411        (global; not used by any task — mypy was chosen for task 03/04)
pre-commit 4.6.1
Python 3.12.9 (global); uv resolved 3.14.0 for nested project venvs
git 2.48.1.windows.1
```

Internet access confirmed available (needed for task 04's pre-commit
hook repos to fetch from GitHub on first run): a throwaway test fetching
`pre-commit/pre-commit-hooks`, `astral-sh/ruff-pre-commit`, and
`pre-commit/mirrors-mypy` all succeeded and built hook environments
without error.

## General method

For every task: ran the validator against the shipped (broken/absent)
state first and confirmed a single clean `NOT PASSED: <reason>` line and
exit 1. Then built a reference fix in `scratch/` (module-root
`.gitignore`'d, never committed), pointed a throwaway copy of that
task's `validate.py` at the scratch copy (only the `TASK_DIR` constant
rewritten — same validator logic, same `harness/common.py` import), and
confirmed `PASSED`. Then deleted `scratch/` entirely and re-ran the real
validator against the untouched task directory to reconfirm it still
fails cleanly (i.e. the shipped stub state was never touched during
authoring).

## Task 01 — uv-project-management

- Stock: `uv run python 01-uv-project-management/tests/validate.py` →
  `NOT PASSED: project/pyproject.toml: [project].dependencies must
  include pyyaml ...` — first structural check, before any subprocess is
  spawned.
- Reference (scratch copy with `dependencies = ["pyyaml>=6"]`,
  `[project.scripts]`, `[dependency-groups].dev = ["pytest>=8"]` added):
  - `uv sync` → resolved 8 packages, built `pricetool` in place.
  - `uv lock --check` → exit 0.
  - `uv run pricetool` → `count=5 min=5.50 max=42.00 avg=17.90
    currency=USD`, exit 0.
  - `uv run pytest -q` → 2 passed.
  - `uv tool run --from . pricetool` → built + installed into an
    ephemeral tool env, same output line, exit 0.
  - Full validator run against the scratch copy → `PASSED`.
- Reverted: scratch removed, real validator re-run → same `NOT PASSED`
  as the first line above, confirming the shipped stub was never
  mutated.

## Task 02 — ruff-lint-and-format

- Stock: → `NOT PASSED: project/pyproject.toml: [tool.ruff].line-length
  must be 100 (got 88)`.
- Investigated rule behavior live before finalizing the fixture:
  - `ruff check` with the stock (implicit-default) select on the given
    `report.py`/`__init__.py` found 6 errors: 2×F401 in `__init__.py`,
    F401/E722/E711/F541 in `report.py`. Confirmed I001 and B006 do
    **not** fire without explicitly selecting `I`/`B` — validates that
    those two families are genuinely "non-default."
  - `ruff check --select E,F,I,B` on the same files found 9 errors,
    adding I001, B006, and (unexpectedly, usefully) E501 — because
    selecting the bare `"E"` prefix pulls in the full E-family including
    E501, not just ruff's narrower implicit default (`E4/E7/E9`). This
    is what makes `line-length` load-bearing rather than a checkbox.
  - Tuned the long line in `report.py` to exactly 92 characters (via a
    small Python length check) so it fails E501 at `line-length=88` but
    passes at `line-length=100` — confirmed both directions live
    (`ruff check --line-length 88 ...` → `E501 ... (92 > 88)`;
    `--line-length 100 ...` → no E501).
- Reference (scratch copy, full config + fully fixed `report.py`):
  - `ruff check src` → `All checks passed!`.
  - `ruff format --check src` → `2 files already formatted`.
  - Tested a cheat scenario too: added a second `per-file-ignores` entry
    exempting `report.py` from E722/B006/E711/F541 (leaving the *code*
    fixed but the *config* over-broad) — validator correctly rejected it
    with `per-file-ignores also covers ['report.py'] — keep the
    exemption scoped to __init__.py only`, confirming that check earns
    its place.
  - Full validator run against the scratch copy → `PASSED`.
- Reverted: scratch removed, real validator re-run → same `NOT PASSED`
  as the first line above.

## Task 03 — typing-strict

- Stock: → `NOT PASSED: project/pyproject.toml: [tool.mypy].strict must
  be set to true (got None)`.
- Investigated live before finalizing:
  - `mypy src` (no `--strict`, config as shipped) → only 1 error
    (`to_currency_code`'s `return-value`) — confirms that specific bug is
    real regardless of strictness, while the other three issues are
    strict-mode-only.
  - `mypy --strict src` → 5 errors: 3×`no-untyped-def`
    (`clean_price`, `parse_optional_tag`, `batch_normalize`), the
    `return-value` error, and 1×`no-untyped-call` (`batch_normalize`
    calling the still-untyped `clean_price`).
  - `pytest -q` on the stock code → 2 failures:
    `test_parse_optional_tag_with_none` (`AttributeError: 'NoneType'
    object has no attribute 'strip'`) and
    `test_to_currency_code_invalid_raises` (`DID NOT RAISE ValueError`)
    — confirms both are live runtime bugs, not just type-checker noise.
- Reference (scratch copy, `strict = true` added, all four functions
  annotated, `parse_optional_tag` given a `None` guard,
  `to_currency_code` raising `ValueError` instead of returning `None`):
  - `mypy src` → `Success: no issues found in 2 source files`.
  - `pytest -q` → 6 passed.
  - Full validator run against the scratch copy → `PASSED`.
- Reverted: scratch removed, real validator re-run → same `NOT PASSED`
  as the first line above.

## Task 04 — pre-commit-wiring

- Stock: → `NOT PASSED: .pre-commit-config.yaml not found — write it,
  it's this task's deliverable`.
- Network/hook-repo reachability confirmed first (see Environment
  section) — this task depends on GitHub being reachable, unlike every
  other task in this module.
- Reference (`.pre-commit-config.yaml` written directly into the real
  task directory, temporarily, then removed — see below): wired all five
  required hooks with `ruff-pre-commit v0.15.7`, `mirrors-mypy v1.7.1`,
  `pre-commit-hooks v5.0.0`.
  - Full validator run → `PASSED: clean fixture passes pre-commit, bad
    fixture is caught by it`.
  - **Bug found and fixed live:** the first pass left
    `04-pre-commit-wiring/scratch/{clean,bad}/repo/.git/` behind after a
    `PASSED` run — `shutil.rmtree(..., ignore_errors=True)` silently
    failed on Windows because git leaves some `.git/` files read-only.
    Fixed `harness/common.py`'s `cleanup_scratch`/`fresh_scratch_dir` to
    use an `onerror` handler that clears the read-only bit (`os.chmod` +
    `stat.S_IWRITE`) and retries. Re-ran the full sequence after the
    fix: `PASSED` again, and confirmed via `find` that no `scratch/`
    directory remained.
- Reverted: the temporary `.pre-commit-config.yaml` was deleted from the
  real task directory (not just scratch) after verification, and the
  validator re-run to confirm the original `NOT PASSED` (file not found)
  reappears — the task directory now contains no config file, matching
  the shipped state.

## Task 05 — packaging-internal-library

- Stock: → `NOT PASSED: project/pyproject.toml:
  [build-system].build-backend must be one of ('hatchling.build',
  'uv_build') (got None)`.
- Reference (scratch copy, `[build-system]` (hatchling),
  `version = "0.4.0"`, `[project.scripts]` added):
  - `uv build --out-dir dist` → built both
    `pricelib-0.4.0.tar.gz` and `pricelib-0.4.0-py3-none-any.whl`.
  - Full validator run against the scratch copy (which internally does
    its own `uv build`, `uv venv`, `uv pip install`, and runs the
    installed script) → `PASSED: src layout, build-system/version/
    entry-point config, uv build, and installed script all checked`.
  - Confirmed cleanup: after the run, `scratch/05-packaging-internal-
    library/project/` contained only `pyproject.toml` and `src/` — no
    leftover `dist/` or venv.
- Reverted: scratch removed entirely, real validator re-run → same
  `NOT PASSED` as the first line above.

## Final sweep

Ran all five validators back-to-back against the final, committed
(broken/absent) state in one pass to confirm none of the individual
verification passes above had mutated a shipped task directory:

```
01-uv-project-management       NOT PASSED (pyyaml missing)
02-ruff-lint-and-format        NOT PASSED (line-length)
03-typing-strict                NOT PASSED (strict flag)
04-pre-commit-wiring            NOT PASSED (config file absent)
05-packaging-internal-library   NOT PASSED (build-backend)
```

All five exit 1 with a single clean line, as expected. `git add -n` on
the whole module directory was inspected to confirm no `.venv/`,
`dist/`, `*.egg-info/`, `__pycache__/`, `scratch/`, or nested
`project/uv.lock` would be staged — only source, config, docs, and the
module-root `uv.lock`.
