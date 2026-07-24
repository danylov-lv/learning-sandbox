# toolkit/t4-git-advanced design notes -- OFF-LIMITS TO THE LEARNER BEFORE FINISHING A TASK

This directory is committed but must not be read before attempting a
task -- see the repo's `CONVENTIONS.md`. There are no reference solutions
here (there never are, anywhere in this repo): this documents the grading
*contract* -- the intended final repo states and the independently-known
answers the validators check against -- not a worked solution.

## Why hardcoded SHAs are used here, and why that's not a reference solution

Every `setup.sh` in this module pins `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`
and file content exactly, `git config core.autocrlf false` +
`core.eol lf` + a `.gitattributes` with `* -text`, and fixed author/
committer identity. That makes every commit SHA in every scratch repo
**fully deterministic** -- the same on every machine, every OS, every
rerun. Verified live: running `setup.sh` twice in a row on this machine
produced byte-identical `git rev-parse main` output both times, for all
of tasks 01-04.

That determinism is what lets tasks 02, 03, and 04 hardcode expected SHAs
directly in `tests/validate.py`, captured once by literally running
`setup.sh` during authoring and reading off `git rev-parse` / `git log`.
This mirrors the spec language for the reflog task precisely ("setup
records the lost SHA in .authoring... for the validator to know the
target") and is not materially different from module 03's
`ground_truth.json` or module 17's independent-recomputation pattern --
the validator's knowledge of the *answer* is not a *solution to the
task*: knowing that main's tip SHA is `b2d59f5...` tells a learner
nothing about how to find and recreate a deleted branch's SHA via
`git reflog`.

## Task 01 -- interactive-rebase-cleanup

**Setup**: 8 commits on `main`, deterministic dates `2024-03-01T09:00`
through `T16:00`, hourly. Two files: `price_alert.py`, `README.md`, plus
a committed `.gitattributes` (`* -text`) to keep line endings out of the
equation entirely.

Commit shape (see `setup.sh` for exact content at each step):
1. `Initial commit` -- `load_config` only.
2. `add threshold check` -- adds `check_threshold`, with a real bug
   (`change_pct > threshold_pct` instead of `abs(change_pct) >=
   threshold_pct` -- misses price *drops* and exact-threshold changes).
3. `Add pric alret logic` -- **typo in the message only**, real content
   (adds `send_alert`, inserted *above* `check_threshold` in the file --
   see the layout note below).
4. `WIP debug` -- adds `debug.log`, a standalone new file, fully
   isolated from both functions. Must be dropped.
5. `fixup! add threshold check` -- fixes commit 2's bug.
6. `add email notification channel` -- extends `send_alert` with a
   `channel` parameter, buggy case-sensitive comparison
   (`channel == "email"`).
7. `fixup! add email notification channel` -- fixes commit 6's bug
   (`channel.lower() == "email"`).
8. `update README` -- adds a Usage section.

**Target**: 5 linear commits -- `Initial commit`, `add threshold check`,
`Add price alert logic` (reworded), `add email notification channel`,
`update README` -- with `debug.log` gone and the two fixups squashed in
(keeping the *target* commit's message, which is exactly `fixup!`
semantics, not `squash!`).

**File-layout gotcha found during live verification (load-bearing,
don't "fix" this by moving things back):** the first draft appended
`send_alert` *after* `check_threshold` in the file. With `--autosquash`,
git moves `fixup! add threshold check` up to sit immediately after
`add threshold check` in replay order -- *before* `Add pric alret logic`
(which adds `send_alert`) gets replayed. That fixup's patch, as
originally recorded, has 3 lines of trailing context after the changed
return line; with the original layout those 3 lines included
`def send_alert(...)`, which doesn't exist yet at that point in the
reordered replay -- a guaranteed `CONFLICT (content)` on `git rebase -i
--autosquash --root`, reproduced live. Moving `send_alert` to sit
*between* `load_config` and `check_threshold` (so `check_threshold` is
always the last function in the file) removes that forward-context
dependency: the threshold fixup's trailing context is now blank
lines/EOF regardless of replay order. Verified live: identical rebase
recipe (`--autosquash --root`, then script `drop`/`reword` via
`GIT_SEQUENCE_EDITOR`/`GIT_EDITOR`) applies with **zero conflicts**
after this reorder. If this task is ever extended with more
fixup/reorder pairs, re-check trailing-context overlap the same way
before shipping.

**Independently-known answer**: the validator hardcodes the expected
final byte-exact content of `price_alert.py` and `README.md` (not
derived by re-running any rebase) plus the exact 5-message list, in
`tests/validate.py`. Live-captured deterministic tip SHA after a correct
cleanup: `2bc9e29ad2ffa080b0f39c81d6f0e52e459f08dd` (stock, pre-cleanup,
8-commit tip: also `2bc9e29...`+ ancestors -- see `setup.sh` for the
full stock log). Note the validator does **not** check this SHA directly
(SHA depends on the exact rebase mechanics/timestamps a learner's
tooling produces) -- it checks message list + linearity + tree content,
which is mechanics-independent.

## Task 02 -- bisect-find-regression

**Setup**: 14 linear commits on `main`, dates `2024-04-01T09:00` through
`T22:00`, hourly. `pricing.sh` (bash, integer arithmetic only -- no
python/other interpreter dependency inside the scratch repo itself) plus
`is_bad.sh`, committed unchanged from commit 1 onward. `is_bad.sh` tests
one fact: `price_after_discount 200 10` must equal `180`.

Regression commit (9th, message `simplify discount formula`) changes the
formula from `amount - amount * pct / 100` to `amount - pct`, breaking
the check (`200 - 10 = 190 != 180`). All 5 remaining commits after it
are unrelated additions (`log_price`, README changelog, a validation
helper, whitespace, a final comment) -- the bug is never touched again,
so bad-ness is monotonic from commit 9 onward, which is required for
`git bisect` to be valid here at all.

Verified live, walking the full 14-commit history and running
`is_bad.sh` at each commit: exactly 8 GOOD then 6 BAD, transition at
commit `f7b636c0ce4fd0e91c0f5e9c3ea36d742715a5f0` ("simplify discount
formula"). This is also what a real `git bisect run bash is_bad.sh`
converged to live (4 steps, as expected for ~14 commits /
log2(14)~3.8). Deterministic across reruns (confirmed: identical
`git rev-parse main` and identical regression SHA on a second `setup.sh`
run).

**Independently-known answer**: the validator does **not** hardcode this
SHA. It walks `work/`'s history itself (oldest to newest) at validation
time, checking out each commit and running `is_bad.sh`, and takes the
first one that fails -- matching the spec's "independently recompute the
first-bad commit by walking history running is_bad.sh." Hardcoding was
avoided here specifically because it's easy and correct to recompute,
unlike tasks 03/04 where the "correct" value isn't a walk-computable
fact so much as "the object git already has."

**Deliverable**: `FIRST_BAD_SHA.txt` at the task root (not inside
`work/` -- it must survive a `setup.sh` rerun, since `work/` gets wiped
every time). Ships with placeholder `PASTE_FULL_SHA_HERE`; validator
special-cases that exact string as "not filled in" before doing anything
else.

## Task 03 -- worktrees-parallel

**Setup**: single commit on `main` (`Initial commit`, date
`2024-05-01T09:00:00+0000`), one file `toolkit-notes.md`. Live-captured
deterministic tip SHA: `e9ac3765fd2318feb5c785ea5bc715606af1eda8`.

**Target**: two worktrees under `work/.worktrees/{alpha,beta}` (kept
inside `work/` specifically so the module's blanket `**/work/` gitignore
covers them without a separate ignore rule), on new branches
`feature/alpha` / `feature/beta`, each exactly one commit ahead of
`main` adding one specified file with one specified line of content and
one specified commit message. `main` must stay at the setup SHA exactly.

**Independently-known answer**: `main`'s expected tip SHA is hardcoded
(captured live, reproducible). The two branches' expected states are
*not* SHA-pinned (a learner's commit will carry whatever timestamp they
committed at, which the task doesn't constrain) -- instead the validator
checks commit-count-ahead-of-main (`1`), exact tip message, and exact
added-file-content, which is the "branch end-state" style the spec
recommends over pinning a SHA that depends on when the learner actually
ran the commands.

**Worktree-list evidence check**: parses `git worktree list --porcelain`
and requires an entry whose resolved `worktree` path matches
`work/.worktrees/{alpha,beta}` and whose `branch` field is exactly
`refs/heads/feature/{alpha,beta}` -- this is what enforces "don't just
create two branches by hand," and also means the learner must leave the
worktrees attached when they run the validator (removing them before
validating fails this check even if the branches themselves are
correct).

## Task 04 -- reflog-rescue

**Setup**: `main` gets an initial commit, then `feature/valuable-work`
branches off and receives two real commits revising `payment-retry.md`,
then `main` gets one more commit (`update notes`, so main visibly
diverges/continues *after* the disaster -- a learner can't just diff
against a static `main`), then `git branch -D feature/valuable-work`
force-deletes the unmerged branch. Dates `2024-06-01T09:00` through
`T12:00`.

Live-captured, deterministic:
- `main` tip: `b2d59f58502657dd74b78d3ef3fa6d042412add6`
- Lost branch tip (`Switch retry design to exponential backoff`):
  `3ce744f4e10a99e00b035bc10d68739ede711090`
- Lost branch's first commit (`Draft payment retry design`):
  `48d6d53dbfec445667fa88f86241aa1bcd605905`

Verified live via `git reflog show HEAD`: the lost tip is directly
visible as a `commit:` entry (from when `HEAD` followed
`feature/valuable-work`), confirmed also via `git fsck --unreachable`
surfacing both dangling commits independently.

**Both SHAs are hardcoded in `tests/validate.py`** (`main`'s expected
tip and the lost branch's expected tip) -- this is the one task in the
module where an exact-SHA match is the entire point: recovery means
pointing a ref at the literal original object (still in the object
database, not yet garbage-collected), not reconstructing equivalent
content in a new commit. A learner who recreates `payment-retry.md` by
hand and commits it fresh will get a *different* SHA (different parent
linkage/timestamps even with identical tree+message) and correctly fail
this check -- verified live by first testing the correct
`git branch feature/valuable-work <sha-from-reflog>` recovery (PASSED),
then confirming a fresh `setup.sh` rerun returns to the stock failing
state.

## Task 05 -- history-design-writeup

Same two-gate doc-gate shape as module 17 (structure + hostile review),
minus the capacity-model gate (there's no numeric model here -- this is
`check_sections` + `check_keywords` + `check_quantitative` +
`check_answers` only, no `import_estimate`/`check_close`).

6 required `##` sections (`Commit granularity and atomicity`, `Commit
message convention`, `Merge strategy: rebase vs merge vs squash`,
`Handling mistakes: amend, revert, and rewriting shared history`,
`Bisectability and blame hygiene`, `Hostile review responses`) and 6
hostile-review questions (`Q1`-`Q6`) in `HOSTILE-REVIEW.md`, each one
deliberately designed to be a direct application of a specific section
above rather than a free-standing new scenario (Q1<->granularity,
Q2<->merge strategy/PR scope, Q3<->merge strategy/rebase-of-shared,
Q4<->message convention, Q5<->message convention's fix vs refactor
taxonomy, Q6<->handling-mistakes' local-vs-shared line) -- so a genuinely
concrete policy answers most of the hostile review "for free," while a
vague one visibly fails to.

`min_hits=9` on a 24-term keyword list, `min_numbers=6` for the
quantitative gate, `min_answered=6`/`min_chars=200` on `check_answers`
with `questions_path=HOSTILE-REVIEW.md` (so verbatim-copy detection
compares against the real question text, not a weak same-line
heuristic -- see module 17's `.authoring/notes-live-verification.md` for
why that flag matters).

Verified live: the stock, unfilled `POLICY.md` fails on `check_sections`
length (several sections' placeholder text sits just under their
`min_chars`, e.g. 288/300) before ever reaching the placeholder-marker or
keyword checks -- still a single clean `NOT PASSED` line, exit 1, no
traceback, which is all the repo convention requires. A throwaway fully
filled `POLICY.md` (concrete numeric rules: 72-char subject limit, a
400-line atomicity signal, a 15-character commit-msg-hook threshold,
etc., all six `### Qn` answered as direct applications of the sections
above) passed cleanly, then was reverted byte-identical to the shipped
template (`diff` confirmed identical) -- no reference solution is
committed anywhere.
