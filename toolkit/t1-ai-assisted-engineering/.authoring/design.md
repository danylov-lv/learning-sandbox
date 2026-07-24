# Design notes -- toolkit/t1-ai-assisted-engineering

Off-limits to the learner before attempting a task -- this file holds
grading-contract detail and, for task 06, planted-bug ground truth.
Read a task's section only after finishing that task, if at all.

## Shared conventions

- Every validator: `guarded` + `not_passed`/`passed` from
  `harness/common.py`, single-line output, exit 0/1, no tracebacks.
- No reference solutions committed anywhere (src, hints, tests,
  `.authoring`). Every throwaway reference used to prove the pass path
  during generation was written, run once, and reverted byte-identical
  (see `notes-live-verification.md`).
- No `docker-compose.yml`, no host ports for this module -- pure Python,
  no services. Consistent with the `CONVENTIONS.md` exceptions already
  documented for modules 16/17/18/19.

## 01-project-memory

Pure doc-gate on `deliverable/CLAUDE.md`: 5 required `##` sections
(`Commands`, `Conventions`, `Architecture`, `What NOT to do`, `Memory vs
rot`), per-section minimum length, no `[fill in`/`TODO:` placeholders,
>=6 grounding keywords specific to the given `sample-project`
(`priceparser`)'s actual contract (money-as-cents, `None`-on-failure,
currency normalization -- not generic Python advice), a regex check that
the file names `sample-project`'s real test invocation
(`pytest\s+tests`), and a separate keyword check on the "Memory vs rot"
section specifically for reflection vocabulary (rot, stale, volatile,
secret, drift, ...).

`sample-project` itself is real, complete, correct code (not a stub) --
`uv run pytest tests -q` from `01-project-memory/sample-project/` passes
8/8 as shipped.

## 02-custom-subagents

Structural: every `.claude/agents/*.md` under `deliverable/` must have
valid YAML frontmatter (`name` + `description` required; `tools`/`model`
well-formed if present) via `harness.common.read_frontmatter`. Requires
an agent with `name: test-runner` and one with `name: code-reviewer`
(exact match -- pinned for determinism, not left to the learner's
naming). `code-reviewer`'s body must have >=6 non-placeholder Markdown
bullet lines (the review checklist). `WHEN-NOT-TO-DELEGATE.md` is doc-
gated the same way as task 01 (3 sections, length, keywords).

## 03-hooks-and-guardrails

Structural + behavioral. `settings.json`'s `PostToolUse` array must have
an entry per required hook filename (`run-tests.py`, `lint.py`, matched
by extracting the last `*.py` token from the `command` string and
resolving `$CLAUDE_PROJECT_DIR`/`${CLAUDE_PROJECT_DIR}` against
`deliverable/`), each with a `matcher` that's tested as a REAL regex via
`re.fullmatch` against both the literal strings `"Edit"` and `"Write"`
(not a substring check -- a learner writing `matcher: "Edit"` alone,
missing `Write`, fails this even though the substring "Edit" trivially
appears).

Behavioral: each hook script is spawned directly (`[sys.executable,
script_path]`, `harness.common.run_hook`), fed a realistic
`PostToolUse` JSON payload on stdin, against 4 fixture dirs under
`tests/fixtures/` (`tests-passing`, `tests-failing`, `lint-clean`,
`lint-dirty`; verified live to actually pass/fail with plain `pytest -q`
/ `ruff check` run with no path args from inside each fixture dir). A
hook "signals failure" if either its exit code is non-zero OR its stdout
parses as JSON with `"decision": "block"` -- both are accepted, matching
the real range of valid Claude Code hook behavior; the reference
implementation used during verification took the JSON path (exit 0
always, block JSON printed on failure), since that's the mechanistically
correct one for `PostToolUse` (which cannot literally undo a completed
Edit/Write).

## 04-headless-and-ci

Purely structural, no live `claude` call, no live GitHub Actions run.
`ai-review.sh`: regex-extracts every `claude` invocation line and
requires each to include `-p`/`--print`; requires `--output-format` and
literal `git diff` somewhere in the file; rejects an interactive `read`
builtin at line start; rejects the shipped stub's exact placeholder
markers.

`ai-review.yml`: YAML-parsed via PyYAML. Load-bearing gotcha documented
in both the validator and the task README/hints: PyYAML's default
(YAML 1.1) resolver reads an unquoted `on:` key as the boolean `True`,
not the string `"on"` -- confirmed empirically during generation
(`yaml.safe_load` on the stub workflow produces `{True: {...}, "jobs":
{...}}`). The validator reads `workflow.get("on", workflow.get(True))`
for exactly that reason. Checks: rejects `push` trigger without a
`pull_request`/`pull_request_target` sibling; requires `types:` on that
trigger to include `"labeled"`; requires some job/step `run:`/`uses:`
containing `claude` + `-p` (or a claude-code-action-shaped `uses:`); and
requires a job- or step-level `if:` whose text contains the substring
`"label"` (case-insensitive) as a proxy for "this actually checks which
label fired the event," not just "any label at all."

A second real gotcha hit while authoring the stub workflow: a `run:`
value that starts unquoted (e.g. `echo "TODO: not implemented"`) but
contains an embedded `": "` inside its own double-quoted portion is
itself invalid YAML (`ScannerError: mapping values are not allowed
here`) -- PyYAML treats the whole thing as a plain scalar since it
doesn't start with a quote, and a colon-space inside a plain scalar is
ambiguous with a nested mapping key. Fixed by removing the colon from
the stub's placeholder message rather than quoting the whole `run:`
value, so the stub stays trivially readable.

## 05-mcp-server

Naming gotcha, load-bearing: the fixture directory is `fixture/`, not
`data/`, even though the original task brief said `05-mcp-server/data/
PROGRESS-fixture.md`. The repo root `.gitignore` has `**/data/`
(intentionally, for the repo-wide convention that generated/seed data
under a `data/` dir is never committed -- see `CONVENTIONS.md`). That
pattern matches ANY directory literally named `data` at any depth, so a
`05-mcp-server/data/` fixture would have been silently gitignored and
never committed -- confirmed empirically with `git check-ignore -v`
before this was caught. Renamed to `fixture/` (not covered by any root
`.gitignore` pattern) to keep the fixture a real, committed, deterministic
file rather than accidentally-untracked content.

Fully behavioral, via the official `mcp` Python SDK client
(`mcp.client.stdio.stdio_client` + `mcp.ClientSession`), never by
importing the learner's `server.py`. `StdioServerParameters(command=
sys.executable, args=[str(SERVER_PATH)], cwd=str(TASK_DIR))`, wrapped in
`asyncio.wait_for(..., timeout=20)`.

Load-bearing implementation note (see the long comment in
`tests/validate.py`): every "expected" grading failure inside the async
protocol exchange (missing tool, tool error, empty content, mismatch)
must be reported by RETURNING a `{"ok": bool, ...}` dict, never by
calling `not_passed()` (which calls `sys.exit`) from inside the `async
with stdio_client(...) / async with ClientSession(...)` blocks. Verified
empirically during generation: those context managers run their own
internal task groups, and Python 3.11+ `TaskGroup.__aexit__` wraps ANY
exception escaping the body -- including a deliberate `SystemExit` --
in an `ExceptionGroup`/`BaseExceptionGroup`, which produced two garbled
`NOT PASSED`-shaped lines instead of one clean one on the first attempt.
Only truly unexpected failures (subprocess never starting, protocol
hang) are handled via a single try/except wrapped around the top-level
`asyncio.run(...)` call in `main()`, outside any task group, with an
explicit `except BaseExceptionGroup` branch alongside the plain
`except Exception` one.

The fixture (`fixture/PROGRESS-fixture.md`) is fixed and small (4 modules,
9 tasks) specifically so the expected answer never depends on the real
repo's PROGRESS.md. First unchecked task, by construction, is
`02-sql-optimization/02-index-design -- choosing and validating
indexes` -- deliberately not the first line of the file or the first
module, so a server that just returns the first task line unconditionally
(ignoring the checkbox) fails.

## 06-verification-discipline -- GROUND TRUTH (spoilers)

Four patches under `patches/patchNN/` (`code.py` + `PR_DESCRIPTION.md`,
never edited by the learner):

| patch | verdict | bug category | the actual defect |
|---|---|---|---|
| patch01 | **BUGGY** | async race | `PerKeyLock.acquire()` awaits (`asyncio.sleep(0)`, framed in the PR as "look up per-key config") BETWEEN checking `self._locks.get(key) is None` and constructing+storing a new `asyncio.Lock()`. Two concurrent first-time callers for the same key both pass the check before either stores a lock, so each ends up with a DIFFERENT lock object -- mutual exclusion for that key silently fails on first concurrent access. Verified empirically deterministic (not flaky): under `asyncio.gather`, two coroutines racing `acquire("k")` get different `id(lock)` on 5/5 runs, and a `enter`/`exit`-ordering probe interleaves as `[A-enter, B-enter, A-exit, B-exit]` on 5/5 runs, both because asyncio's single-threaded cooperative scheduler gives a fixed interleaving for a fixed coroutine/await-point structure. |
| patch02 | **BUGGY** | off-by-one (slicing) | `paginate()` computes `end = start + page_size - 1`, then slices `items[start:end]` -- Python slicing is already exclusive of `end`, so this returns only `page_size - 1` items per page. The dropped item (index `page_size - 1` of each page) never appears on ANY page -- real data loss, not just a cosmetic short page. `paginate(list(range(10)), 0, 5)` returns `[0,1,2,3]`, not `[0,1,2,3,4]`. |
| patch03 | **BUGGY** | silent type coercion | `is_feature_enabled()` returns `bool(config.get(key, False))`. `bool("false")` is `True` in Python -- any config source that hands back a string-typed boolean (env vars; a remote/JSON-as-string config service, which the PR description itself claims this function must handle) silently flips a disabled flag to enabled. `is_feature_enabled({"x": "false"}, "x")` returns `True`. |
| patch04 | **CLEAN** | (control) | `chunk()` via `range(0, len(items), size)` + `items[i:i+size]` is correct: no trailing empty chunk on an exact multiple, correct smaller final chunk on a remainder, correct empty-input result, and an explicit `ValueError` guard on non-positive `size` (redundant with `range`'s own behavior for `size == 0`, which already raises `ValueError: range() arg 3 must not be zero`, but the guard also correctly rejects negative sizes, which bare `range` would otherwise silently treat as zero iterations rather than erroring). Deliberately styled similarly to patch02 (same slicing-in-a-comprehension shape) so verdict discrimination isn't just "does it look like the buggy one." |

`REVIEW.md` grading: `harness.common.check_answers` doc-gates the four
`### patchNN` subsections (presence, length >=120 chars, not a
placeholder, not mostly copied from that patch's own
`PR_DESCRIPTION.md` -- diffed against `tests/pr-descriptions-combined.md`,
a committed concatenation of all four descriptions, `min_original_chars
=80`). Separately, a `Verdict:\s*(BUGGY|CLEAN)` regex is extracted from
each subsection and compared against the `GROUND_TRUTH` dict hardcoded
directly in `tests/validate.py` (not read from this file at runtime --
this file is the human-readable spoiler copy of the same facts).

`tests_learner/test_patchNN.py` grading: each file is run ALONE as its
own fresh `pytest` subprocess (`harness.common.run_pytest`) with
`cwd=TASK_DIR`, against the code exactly as shipped -- there is
deliberately no hidden "fixed" variant anywhere for the validator to
swap in and compare against (unlike module 16's mutant-bank pattern).
This is intentional and matches the actual instruction given for this
task: the validator only needs to prove the learner's test "genuinely
catches the planted bug" by failing against the shipped buggy code (and
passing against the shipped clean control) -- it does not need to also
prove the test would go green after a hypothetical fix, since no
reference fix is committed anywhere. The README explicitly tells the
learner that manually fixing a patch locally to sanity-check their test
goes green afterward is a good habit, but it is not something the
validator automates or checks.

Anti-gaming: (a) both directions are required across all 4 patches, so
a suite that's `assert True` everywhere fails the 3 BUGGY patches'
"must FAIL" requirement, and a suite that's `assert False` everywhere
fails the CLEAN control's "must PASS" requirement -- neither trivial
strategy clears both; (b) each test file must contain the literal
substring of its own patch id (e.g. `"patch02"`), a cheap structural
check against a copy-pasted-but-unrelated test file; (c) `collected >= 1`
per file (a `pytest.skip(...)`-only stub, exactly what's shipped in the
stock stub, counts as collected but not failed, which correctly fails
the "must FAIL" check for BUGGY patches on the stock state).
