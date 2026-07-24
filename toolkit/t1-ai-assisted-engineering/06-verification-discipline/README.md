# 06 -- Verification Discipline

## Backstory

Every other task in this module is about using Claude Code well. This
one is about the skill that matters most once you do: reviewing AI-
generated (or anyone else's) code you didn't write, that comes with a
plausible-sounding description of what it does, and deciding whether to
trust it. A plausible PR description is not evidence the code is
correct -- it's evidence someone (or something) believed it was correct,
which is a different claim entirely.

Four small patches are shipped here, each with real code and a real PR
description written the way a real PR description reads: confident,
specific, slightly reassuring. Three of them are wrong in a way that
would pass a skim and a quick manual test. One is genuinely fine. Your
job is the actual job: read the code like you own the consequences of
being wrong, decide which is which, and then prove your review holds up
by writing a test that would actually catch the problem -- not just a
test that runs the function.

## What's given

- `patches/patch01/` .. `patches/patch04/` -- each a `code.py` (the
  "patch") and a `PR_DESCRIPTION.md` (the PR body). Read-only; you do not
  edit these.
- `REVIEW.md` -- unfilled template, one `### patchNN` subsection per
  patch.
- `tests_learner/test_patch01.py` .. `test_patch04.py` -- stubs, each
  currently just `pytest.skip(...)`.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked. Ground truth is NOT in this repo anywhere you
  can read before finishing -- see "Off-limits" below.
- `hints/` -- three levels of hints, including one worked example of the
  test-writing skill on a bug shape that isn't any of the four here.

## What's required

For each of the four patches:

1. Decide **BUGGY** or **CLEAN** and write your verdict plus your actual
   reasoning (grounded in the code, not a restatement of the PR
   description) in `REVIEW.md`.
2. Write a real test in `tests_learner/test_patchNN.py` that:
   - **FAILS** when run against the shipped `patches/patchNN/code.py` if
     you called it BUGGY, or
   - **PASSES** against the shipped code if you called it CLEAN.

A test that always fails (regardless of the code) or always passes
(regardless of the code) does not satisfy this -- the validator checks
both directions across all four patches, so a suite that games one
direction fails the other.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 06-verification-discipline/tests/validate.py
```

It checks, in order:

- `REVIEW.md`'s four `### patchNN` subsections are genuinely answered
  (present, long enough, not a placeholder, not mostly copied from the
  patch's own `PR_DESCRIPTION.md`).
- Each subsection's `Verdict: BUGGY`/`Verdict: CLEAN` line matches this
  task's ground truth.
- Each `tests_learner/test_patchNN.py`, run individually as its own real
  `pytest` subprocess against the shipped `patches/patchNN/code.py`,
  behaves as required: FAIL for every BUGGY patch, PASS for the CLEAN
  one. Each test file must also collect at least one real test and
  reference its matching patch's module.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Code review as a distinct skill from code writing: what a reviewer
  checks that a skim doesn't catch
- Common categories of subtle, plausible-looking bugs: race conditions
  around shared mutable state, off-by-one errors at slice/range
  boundaries, implicit type coercion changing truthiness or comparison
  behavior
- `asyncio`'s single-threaded cooperative scheduling model, and why that
  makes certain async race conditions fully deterministic to reproduce
  in a test (no real concurrency or timing needed)
- The difference between a test that exercises code and a test that
  actually pins down its contract (what a "meaningless assertion" looks
  like, and how to spot one in your own test)
- Trusting (or not trusting) a PR/commit description as a proxy for what
  the code actually does

## Off-limits

`.authoring/design.md` (at the module root) holds the ground truth for
this task (which patches are buggy, and why) -- read it only after you've
submitted your own review, not before. Reading it first defeats the
entire point of the task.
