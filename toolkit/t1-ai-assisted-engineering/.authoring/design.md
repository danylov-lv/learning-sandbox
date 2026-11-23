# Authoring contracts: toolkit/t1-ai-assisted-engineering

Learner off-limits before attempting a task. Task 06 contains grading ground truth.

## Shared conventions

Validators use harness/common.py for PASSED / NOT PASSED output and exit 0/1. The module has no services or host ports. Learner deliverables remain unsolved; active agent configuration belongs outside the exercise templates. Dependency versions come from pyproject.toml and uv.lock.

## 01-project-memory

Grade deliverable/AGENTS.md using the five required sections, per-section length checks, placeholder detection, sample-project grounding, its pytest command, and the memory-versus-rot reflection vocabulary. The exact rubric lives in tests/validate.py. The draft is not active instructions for sample-project; optional discovery trials use a temporary project.

## 02-custom-subagents

Parse deliverable/.codex/agents/*.toml. Require unique test-runner and code-reviewer names, non-placeholder name/description/developer_instructions strings, and at least six reviewer checklist bullets. Optional model settings are strings; omit them for inheritance. Reject fields outside the task subset. Apply the document gate to WHEN-NOT-TO-DELEGATE.md. These checks do not spawn agents or validate model availability.

## 03-hooks-and-guardrails

Read synchronous PostToolUse handlers from deliverable/.codex/hooks.json. Commands reference .codex/hooks/run-tests.py and .codex/hooks/lint.py relative to the project root. Match apply_patch or both Edit/Write aliases.

Invoke each script with a Codex apply_patch JSON payload against the passing/failing pytest fixtures and clean/dirty ruff fixtures. The payload carries cwd and tool_input.command. Clean fixtures require exit 0 without block feedback. Bad fixtures require exit 2 with stderr feedback or exit 0 with decision:block and a non-empty reason. A crash is not valid feedback; a completed edit cannot be undone by this event.

## 04-headless-and-ci

Structurally inspect the script for git diff, non-interactive codex exec, --json, and explicit --sandbox read-only without conflicting flags. Output is JSONL. Parse the workflow with PyYAML, accepting its boolean True representation of the on key. Require only pull_request/types:[labeled], a specific-label equality on the actual review job or step, and a supported review invocation with read-only settings. These checks do not run the model or hosted CI.

## 05-mcp-server

Use fixture/PROGRESS-fixture.md rather than a data directory, since generated data directories are gitignored. Grade the stdio handshake, tool discovery, and next_recommended_task response through the official MCP Python client with a 20-second timeout. Compute the answer from the fixed fixture, independently of the learner's implementation and the repository's changing progress.

Return expected protocol failures as result dictionaries from inside async context managers; report NOT PASSED after they exit. Raising SystemExit inside their task groups can wrap it in an exception group and damage the failure output. Keep subprocess startup and timeout handling outside the protocol context.

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
