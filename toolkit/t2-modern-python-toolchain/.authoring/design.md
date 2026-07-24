# Design notes — t2-modern-python-toolchain

Off-limits to the learner until after they finish a task (see module
README and CONVENTIONS.md). This documents the grading contract and the
planted-issue ground truth per task, for future authoring sessions to
resume from without re-deriving everything.

## Shared harness (`harness/common.py`)

- `guarded`/`passed`/`not_passed` — copied verbatim in spirit from
  `17-system-design/harness/common.py` (same one-line PASSED/NOT PASSED
  contract), but this module's tasks are behavioral/subprocess-driven
  rather than doc-graded, so the doc-section-parsing half of that file
  was dropped and replaced with:
  - `run()` / `require_success()` / `require_failure()` — subprocess
    wrappers that never raise on nonzero exit; the caller decides what a
    given exit code means.
  - `load_toml()` / `load_yaml()` — config parsing (stdlib `tomllib`;
    `pyyaml` for YAML, hence the module-root `pyyaml>=6` dependency).
  - `count_pattern()` / `iter_py_files()` — regex counting across source
    files, used to cap `# noqa` (task 02) and `# type: ignore` (task 03).
  - `fresh_scratch_dir()` / `cleanup_scratch()` — scratch-dir lifecycle
    for tasks 04/05, which need a throwaway git repo / venv. On Windows,
    a throwaway git repo's `.git/objects/pack/*.pack` files are
    sometimes read-only, so `shutil.rmtree` needs an `onerror` handler
    that clears the read-only bit and retries — plain `ignore_errors=True`
    silently leaves the directory behind. Discovered live during task 04
    verification (see notes-live-verification.md).

## Tool invocation strategy

`ruff`, `mypy`, and `pre-commit` are pinned in this module's own
`[dependency-groups].dev` (module-root `pyproject.toml`) and invoked as
plain `["ruff", ...]` / `["mypy", ...]` / `["pre-commit", ...]` — no
`uv run` prefix inside the validator. This works because the validator
itself is always launched via `uv run python .../validate.py`, which
prepends the module's own `.venv/Scripts` (or `bin`) to `PATH` for the
python subprocess it starts; `subprocess.run` in `harness.common.run()`
inherits that `PATH` by default, so the plain binary name resolves to
the pinned dev-group version, not whatever's globally on the machine's
PATH. Verified live: module dev-group installed `ruff==0.16.0` /
`mypy==2.3.0` while the machine's global installs were `ruff==0.15.7` /
`mypy==1.7.1` at authoring time — the pinned versions were the ones
actually exercised.

Task 01 is the one exception: it specifically exercises `uv` itself
(`uv sync`, `uv run`, `uv tool run`), so its validator shells out to
`uv` directly rather than through this indirection.

## Task 01 — uv-project-management

**Ground truth (stock/broken state):** `project/pyproject.toml` has
`dependencies = []` (missing `pyyaml`, which `pricetool.cli` imports),
no `[project.scripts]`, no `[dependency-groups]`. `[build-system]` is
already correct in the stock state (hatchling, `packages =
["src/pricetool"]`) — packaging depth is task 05's concern, not this
one's, so it's given rather than planted.

**Data fixture:** `PRICES = [19.99, 5.50, 42.00, 13.25, 8.75]`, config
embedded as a YAML string (`currency: USD`) inside
`src/pricetool/data.py` rather than a loose file on disk — this was a
deliberate design choice after realizing `uv tool run --from .` builds
and installs the project into an ephemeral env, so any data file living
outside `src/pricetool/` (e.g. a top-level `data/prices.json`) would not
ship in the wheel and the tool-run step would break differently than the
`uv run` step. Embedding the fixture inside the package sidesteps that
entirely.

Expected `pricetool` output: `count=5 min=5.50 max=42.00 avg=17.90
currency=USD` (avg = 89.49 / 5 = 17.898 → 17.90).

**Required fix:**
```toml
dependencies = ["pyyaml>=6"]

[project.scripts]
pricetool = "pricetool.cli:main"

[dependency-groups]
dev = ["pytest>=8"]
```

**Validator gates:** structural (pyyaml present, script entry exact
match, dev group has pytest) → `uv sync` succeeds → `uv.lock` exists →
`uv lock --check` → `uv run pricetool` output matches → `uv run pytest
-q` passes → `uv tool run --from . pricetool` output matches (same
regex-based numeric check, tolerant to ±0.01 on the float fields).

`uv tool run --from . <name>` is the flag-explicit form of `uvx --from .
<name>`; both build the project into an ephemeral tool env and run the
entry point from there, distinct from `uv run` inside the project's own
synced `.venv`. This is what satisfies the top-level spec's "using uv
for a TOOL (e.g. uv tool/uvx)" requirement, tied to the same entry point
rather than an unrelated third-party tool — kept it in-scope and
non-flaky (no persistent global install to clean up afterward, unlike
`uv tool install`).

## Task 02 — ruff-lint-and-format

**Ground truth (stock/broken state):** `project/pyproject.toml` has only
`[tool.ruff]` with `line-length = 88` (ruff's own default value — i.e.
functionally unset). No explicit `select`, no `per-file-ignores`.

**Planted issues in `project/src/reportkit/report.py`:**
- `import sys` — entirely unused (F401), must be *removed*, not ignored.
- Import block order `sys, Path, json` — unsorted per isort convention
  (I001); even after `sys` is deleted, `Path`/`json` are still in the
  wrong relative order (isort sorts by module name: `json` < `pathlib`).
- `def summarize(rows, seen=set()):` — mutable default argument (B006).
- `except:` (bare) — E722 (already in ruff's *default* select via the E7
  subset, no extra config needed to catch it, but still a real fix
  required).
- `if status == None:` — E711 (also in default E7 subset).
- `f"No rows found"` — F541, placeholder-less f-string.
- `note = f"Processed ... status ok"` line is exactly 92 characters —
  fails `E501` at `line-length=88`, passes at the required
  `line-length=100`. This only matters because the required `select`
  includes the *broad* `"E"` prefix (not ruff's narrower implicit
  default of `E4/E7/E9`) — selecting `"E"` explicitly pulls in `E501`,
  which is what makes the `line-length` value load-bearing rather than
  cosmetic. Verified live: `ruff check --line-length 88 --select
  E,F,I,B` flags E501 on this line; `--line-length 100` does not.
- Format-only issues (no lint rule, just `ruff format` non-canonical
  style): `total+=row["amount"]` (no spaces), `status = 'unknown'`
  (single quotes), missing blank line before `def build_report`.

**`project/src/reportkit/__init__.py`:** re-exports `build_report` and
`summarize` for `from reportkit import ...` — deliberately triggers F401
twice, the canonical case for a scoped `per-file-ignores` entry (no
`__all__` added, on purpose — that would sidestep the need for the ruff
config entirely).

**Required config:**
```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
```

**Validator gates:** structural (line-length == 100 exactly; select
covers all four prefixes E/F/I/B, checked via `code == prefix or
code.startswith(prefix)` so either bare prefixes or specific codes
satisfy it; no `"ALL"` in select/ignore; per-file-ignores has exactly one
key matching `__init__.py` containing F401, and no other file is
exempted) → `ruff check src` exits 0 → `ruff format --check src` exits 0
→ independent regex re-checks on `report.py`'s raw source that `import
sys`, the bare `except:`, the `seen=set()`/`seen=[]`/`seen={}` default,
`== None`, and a placeholder-less f-string are all gone → `# noqa` count
under `src/` capped at 0.

## Task 03 — typing-strict

**Ground truth (stock/broken state):** `project/pyproject.toml`'s
`[tool.mypy]` has `python_version` and `mypy_path = "src"` set (given
correct — this task is specifically about the `strict` flag, not mypy
plumbing) but no `strict` key at all.

**Planted issues in `project/src/normkit/normalize.py`:**
- `clean_price(value)` — no annotations at all (`no-untyped-def` under
  strict).
- `parse_optional_tag(tag=None)` — no annotation on a parameter whose
  default is `None`; separately, the body calls `tag.strip()`
  unconditionally, which is a **live runtime bug** (`AttributeError` on
  `None`), not just a type-checker complaint. This is deliberate: fixing
  only the annotation (`tag: str | None = None`) without adding the
  `is None` guard still fails strict (`tag.strip()` on a possibly-`None`
  value) *and* still fails the given pytest test — the two gates
  reinforce each other here.
- `to_currency_code(code: str) -> str:` returns `None` on the invalid
  path — `return-value` error under strict (and under plain mypy too,
  verified live: this specific error fires even without `--strict`,
  since it's a real signature violation, not a leniency-gated check).
  The given test (`test_to_currency_code_invalid_raises`) expects a
  `ValueError`, not `None` — the fix must change control flow (raise),
  not just satisfy the type checker with a cast or an ignore.
- `batch_normalize(prices)` — no annotations (`no-untyped-def` +
  `no-untyped-call` when it calls the now-typed `clean_price`).

**Given, unedited `project/tests/test_normalize.py`** pins exact
behavior for all four functions, including the two cases above that are
currently broken at runtime (`parse_optional_tag(None) == ""`,
`to_currency_code("dollars")` raises `ValueError`). This is what
prevents "fix" via blanket `# type: ignore` or by loosening the
signatures — the pytest gate is independent of the mypy gate and checks
actual behavior.

**Validator gates:** structural (`[tool.mypy].strict is True`, exactly)
→ `mypy src` exits 0 → `pytest -q` exits 0 against the given, unedited
test file → `# type: ignore` count under `src/` capped at 0 (all four
issues are cleanly fixable without one — verified live via the reference
fix below).

## Task 04 — pre-commit-wiring

**Ground truth (stock/broken state):** no `.pre-commit-config.yaml` in
the task directory at all — it is the deliverable, not a scaffold to
repair.

**Fixtures (both committed, static, not authored by the validator at
runtime):**
- `fixtures/clean/statkit/stats.py` — `mean`/`variance`, fully annotated,
  ruff-clean, ends with a newline, no trailing whitespace. Hooks must
  pass on this with zero modifications.
- `fixtures/bad/statkit/stats.py` — same shape, four problems planted at
  once: `import os` (unused, F401), `def mean(values):` (no annotations,
  caught only under `mypy --strict`), a trailing-whitespace line
  (`import os   \n`, injected via a raw byte edit since the normal
  editor tooling strips trailing whitespace on save), and no final
  newline at EOF (file literally ends mid-line, no `\n` byte).

**Required `.pre-commit-config.yaml`** (task dir root, not inside
`fixtures/`): five hook ids across three repos —
`astral-sh/ruff-pre-commit` (`ruff`, `ruff-format`),
`pre-commit/mirrors-mypy` (`mypy`, with `args: [--strict]`),
`pre-commit/pre-commit-hooks` (`trailing-whitespace`,
`end-of-file-fixer`). Live-verified all three repos are reachable and
their hook environments build successfully in this environment
(internet access confirmed — see notes-live-verification.md) with these
pinned revs: `ruff-pre-commit v0.15.7`, `mirrors-mypy v1.7.1`,
`pre-commit-hooks v5.0.0` (matching the machine's globally-installed
tool versions at authoring time, though the validator does not check
which rev the learner pins — only that hooks are wired, `--strict` is
present, and the behavioral gates pass).

**Validator flow:** structural YAML check (all five hook ids present;
mypy hook's `args` contains `--strict`) → copy the clean fixture plus the
learner's config into a fresh throwaway git repo under `scratch/clean/`,
`git init` + `git add -A`, run `pre-commit run --all-files`, require exit
0 → copy the bad fixture into a second throwaway repo under
`scratch/bad/`, same config, run again, require **nonzero** exit and
that the combined output contains the literal string `"Failed"` (guards
against a config error producing a nonzero exit for the wrong reason) →
`scratch/` removed in a `finally` block regardless of outcome.

**Windows gotcha (see harness section above):** the first implementation
of `cleanup_scratch` used `shutil.rmtree(path, ignore_errors=True)`,
which silently left `scratch/clean/repo/.git/` and
`scratch/bad/repo/.git/` behind on Windows (read-only pack files inside
a git repo). Fixed by adding an `onerror` handler that clears the
read-only bit and retries. Confirmed fixed live: a second full run left
no `scratch/` directory behind.

## Task 05 — packaging-internal-library

**Ground truth (stock/broken state):** `project/pyproject.toml` has only
`[project]` `name`/`description`/`requires-python`/`dependencies = []` —
no `[build-system]`, no `version`, no `[project.scripts]`. `uv build`
fails immediately on this (no build backend to even attempt with).

**Given, unedited library:** `src/pricelib/__init__.py` has
`__version__ = "0.4.0"` and `summarize()`; `src/pricelib/cli.py` prints
`pricelib {__version__}: count={n} avg={avg:.2f}` for a fixed
`SAMPLE_PRICES = [12.5, 7.25, 30.0, 4.99]` (avg = 54.74 / 4 = 13.685 →
`13.69`, `.2f` rounding verified live).

**Required fix:**
```toml
[project]
version = "0.4.0"        # must match __version__ exactly

[project.scripts]
pricelib = "pricelib.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pricelib"]
```
(`uv_build` is accepted as an equally valid backend by the validator;
only `hatchling` was exercised in the live reference-solution pass.)

**Validator gates:** structural (`src/pricelib/` exists, no stray flat
`project/pricelib/` alongside it; `[build-system].build-backend` is
`hatchling.build` or `uv_build`; `[project].version` present and equal
to the `__version__` regex-extracted from the given `__init__.py`
source — never imported, to avoid needing the package installed just to
check its own metadata; `[project.scripts]` maps `pricelib` to
`pricelib.cli:main` exactly) → `uv build --out-dir dist` succeeds →
both a `*.whl` and a `*.tar.gz` exist under `project/dist/` → a
throwaway venv is created under `scratch/venv/` via `uv venv` → the
built wheel installs into it via `uv pip install --python <venv>
<wheel>` → the *installed* script (`scratch/venv/Scripts/pricelib.exe`
on Windows, `scratch/venv/bin/pricelib` on POSIX — resolved by checking
which path exists, not by `sys.platform`) is invoked directly (not
`uv run`) and its stdout is checked against the independently-recomputed
expected version/count/avg → `scratch/` and `project/dist/` are removed
in a `finally` block regardless of outcome.

## Cross-task conventions

- Every task's "broken" `project/pyproject.toml` is the **only** file
  the learner edits for tasks 01/02(config half)/03/05; 02's source file
  and 04's fixtures are also learner-edited/authored respectively where
  the task is about code/config rather than pure tool config.
- No task's validator ever imports learner-controlled code as a Python
  module (risk of arbitrary code execution / import side effects at
  validation time) — task 03's mypy/pytest gates run mypy and pytest as
  *subprocesses*, not via `importlib`. Task 05 extracts `__version__` via
  regex on the given (unedited) source rather than importing it.
- All five tasks were verified with the stock/broken state left in the
  repo (never a reference solution) — see notes-live-verification.md for
  the exact sequence run for each.
