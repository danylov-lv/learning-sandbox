# Live verification notes -- toolkit/t1-ai-assisted-engineering

Spoilers. Read after finishing the module, not before.

## Environment

`uv lock` + `uv sync` run once at the module root. Resolved 38 packages;
key ones installed: `pytest==9.1.1`, `mcp==1.28.1`, `pyyaml==6.0.3`
(plus `mcp`'s own transitive deps: `httpx`, `pydantic`, `starlette`,
`uvicorn`, `sse-starlette`, etc.). `ruff 0.15.7` and `claude` confirmed
present on the machine's PATH as globally-installed tools (not module
dependencies -- see task 03's design note).

## What was verified, per task

For every task: ran `tests/validate.py` against the shipped stock stub
first (confirmed a single `NOT PASSED: <reason>` line, exit 1, no
traceback lines on stdout), then wrote a throwaway reference solution in
place, confirmed `PASSED` and exit 0, then reverted every touched file
byte-for-byte back to its stub content and re-confirmed both the
`sha256sum` match and the stock `NOT PASSED` behavior again post-revert.
No reference solution is committed anywhere.

- **01-project-memory**: `sample-project`'s real test suite
  (`uv run pytest tests -q` from `sample-project/`) passes 8/8 as
  shipped (it's given, correct code, not a stub). Stock
  `deliverable/CLAUDE.md` fails on `section(s) too short` (four
  sections under their min-char floor). Reference filled all 5 sections
  with sample-project-grounded content -> `PASSED`. Reverted, sha256
  matched, re-fails identically.

- **02-custom-subagents**: stock frontmatter uses quoted YAML strings
  like `name: "TODO: fill in -- must be exactly test-runner"` specifically
  so the file stays valid YAML (a bare `[fill in: ...]` value would have
  been parsed as a YAML flow sequence and either errored unpredictably or
  parsed as a list, not a placeholder string -- caught and fixed during
  authoring before this was ever run). Stock fails on the first
  placeholder frontmatter field encountered (`code-reviewer.md`'s
  `name`). Reference: 2 agents with matching `name: test-runner` /
  `name: code-reviewer`, an 8-item checklist, filled
  `WHEN-NOT-TO-DELEGATE.md` -> `PASSED` ("2 agent(s) validated,
  code-reviewer checklist has 8 items"). Reverted, sha256 matched.

- **03-hooks-and-guardrails**: fixtures verified independently before
  wiring the validator to them -- `python -m pytest -q` from inside
  `tests-passing/` exits 0 (1 passed), from `tests-failing/` exits 1 (1
  failed); `ruff check` (no path arg) from inside `lint-clean/` exits 0
  ("All checks passed!"), from `lint-dirty/` exits 1 (3 real violations:
  2x F401 unused import, 1x F841 unused variable). Stock hook scripts
  `raise NotImplementedError` -> validator's first behavioral check
  (passing fixture must exit 0) correctly fails with the
  `NotImplementedError` traceback tail visible in the reported reason
  (still a single `NOT PASSED:` line, since the traceback text is
  embedded as one line's payload, not printed separately). Reference:
  both scripts read `CLAUDE_PROJECT_DIR`, shell out via
  `sys.executable -m pytest -q` / `ruff check`, print
  `{"decision":"block",...}` JSON on non-zero exit, else exit 0 with no
  JSON -> `PASSED` against all 4 fixtures. Reverted, sha256 matched both
  files.

- **04-headless-and-ci**: confirmed empirically that PyYAML's default
  (YAML-1.1) resolver parses an unquoted `on:` key as the boolean `True`
  (`yaml.safe_load` on the stub workflow yields `{'name': ..., True:
  {'push': {'branches': ['main']}}, 'jobs': ...}`) -- the validator
  reads `workflow.get("on", workflow.get(True))` for exactly this
  reason, and the task's hints call this out explicitly since it's a
  real pitfall independent of this exercise. Also hit and fixed a second
  YAML gotcha while writing the STUB itself: an unquoted `run: echo
  "TODO: not implemented"` line is a YAML `ScannerError` ("mapping
  values are not allowed here") because the value starts unquoted and
  the embedded `": "` inside its own quotes reads as an ambiguous nested
  mapping key -- fixed by rewording the stub's placeholder text to avoid
  an embedded colon rather than quoting the whole `run:` value. Stock
  script/workflow fail cleanly (`still contains the unfilled stub body`).
  Reference script + workflow (real `git diff`-based prompt,
  `--output-format json`, `--allowedTools`; workflow with
  `pull_request: {types: [labeled]}`, an `if:` on
  `github.event.label.name`, and an `npm install -g
  @anthropic-ai/claude-code` + `claude -p ... --output-format json`
  step) -> `PASSED`. No live `claude` call or live Actions run involved,
  per spec. Reverted, sha256 matched both files.

- **05-mcp-server**: confirmed the `mcp` SDK's stdio client API surface
  live (`StdioServerParameters`, `stdio_client`, `ClientSession`,
  `FastMCP`) via `uv run python -c "..."` before writing the validator,
  to avoid guessing at an API shape. Hit the ExceptionGroup-wrapping
  issue documented at length in both `tests/validate.py`'s module
  docstring and `.authoring/design.md`'s task-05 section -- fixed by
  having the async protocol code RETURN `{"ok": ...}` instead of calling
  `not_passed()` (which is `sys.exit`) from inside the `async with`
  blocks; confirmed the fix produces exactly one `NOT PASSED:` line on
  stdout (verified separately with stderr redirected to `/dev/null`,
  since FastMCP's default request logging goes to the subprocess's
  stderr, not stdout -- that logging output is harmless noise on stderr,
  never on the stdout stream the "one line" convention actually governs).
  Stock server `raise NotImplementedError` inside the tool -> validator
  reports the MCP error text cleanly. Reference implementation (same
  parsing logic later also used independently in the validator, written
  separately) -> `PASSED` with the expected fixture answer
  `02-sql-optimization/02-index-design -- choosing and validating
  indexes`. Reverted, sha256 matched.

- **06-verification-discipline**: the async-race patch's determinism was
  verified empirically BEFORE writing hints/design docs around it, not
  assumed -- 5/5 runs of a concurrent `acquire("k")` probe against the
  shipped `patch01/code.py` produced different `id(lock)` values, and
  5/5 runs of an enter/exit-ordering probe produced the identical
  interleaved order `[A-enter, B-enter, A-exit, B-exit]`, confirming
  asyncio's single-threaded cooperative scheduling makes this "race"
  fully reproducible without flakiness (no real threads, no real I/O,
  no timing sensitivity). Stock `REVIEW.md`/`tests_learner/*` (all
  `[fill in ...]` placeholders / `pytest.skip(...)` stubs) fails on the
  doc-gate: `only 0/4 required subsection(s) genuinely answered`.
  Reference: correct verdicts + grounded reasoning in `REVIEW.md`, and 4
  real test files (an async ordering probe for patch01, a page-content +
  round-trip check for patch02, two truthiness checks for patch03, and
  4 boundary checks for patch04) -> `PASSED`. Reverted all 5 touched
  files, sha256 matched every one.

## Anti-hardcode / anti-gaming spot checks

- 01/02/04: re-ran each validator a second time after reverting to
  confirm the exact same `NOT PASSED:` reason string reproduces
  deterministically (no flakiness from e.g. dict ordering or set
  iteration in the keyword-matching helpers).
- 03/05/06 (subprocess-based): re-ran the full stock-fail -> reference-
  pass -> revert-refail cycle end to end a second time for 03 and 06
  specifically, since these two run real child `pytest`/hook
  subprocesses and were the highest-risk for nondeterminism; both
  reproduced identically both times.
- 06 specifically: reasoned through (documented in `design.md`'s
  "Anti-gaming" note) why an always-`assert True` or always-`assert
  False` learner suite cannot clear both the BUGGY and CLEAN
  requirements simultaneously, since the validator checks both
  directions across all 4 patches rather than any single patch in
  isolation.

## Final state

`git status --porcelain` inside `toolkit/t1-ai-assisted-engineering`
shows only intentionally-committed files -- `.venv/`, `.pytest_cache/`,
and `__pycache__/` directories created by the `uv sync` / validator runs
above are all covered by the repo root `.gitignore`
(`**/.venv/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`) and were
confirmed absent from `git add --dry-run` / `git status` output before
finishing.
