No ready-made verdicts or tests here — just the exact mechanics the
validator checks, so you know what "done" looks like structurally, and
one worked-through example of the TESTING skill (not the verdict) using
a pattern deliberately NOT reused from the four real patches.

**REVIEW.md contract:** four `### patchNN` subsections, each starting
with a line matching exactly `Verdict: BUGGY` or `Verdict: CLEAN`
(case-insensitive, but spell it clearly), followed by your own reasoning
-- long enough, and not close enough to the patch's own `PR_DESCRIPTION.md`
text to look copied (the validator diffs your answer against the actual
PR description text, not just a length check).

**tests_learner/test_patchNN.py contract:** import from
`patches.patchNN.code` (e.g. `from patches.patch02.code import
paginate`) -- the validator greps for the literal string `"patch02"`
inside your test file as a lightweight check that you're actually
testing the right module, not something unrelated. Then it runs your
file alone, as its own `pytest` subprocess, against the code exactly as
shipped (there is no separate "fixed" version anywhere for it to swap
in) and checks the outcome: for a patch you called BUGGY, your test
must actually FAIL against that shipped code; for the CLEAN control, it
must PASS.

**A worked example of the test-writing skill on a DIFFERENT bug shape**
(not any of the four in this task, so it's not a spoiler): suppose a
function is supposed to return the average of a list but silently
returns `0` for an empty list instead of raising. The trivial test
`assert average([]) is not None` would pass on both the buggy and a
correct version -- it doesn't distinguish them, so it "catches" nothing.
The test that actually catches the bug asserts the SPECIFIC wrong
behavior directly, e.g. `with pytest.raises(ValueError): average([])` --
that fails loudly against the buggy version (which returns `0` instead
of raising) and passes against a version that raises correctly. That
distinction -- a test that merely runs the code vs. one that pins down
the exact contract that's actually at risk -- is the whole point of this
task.
