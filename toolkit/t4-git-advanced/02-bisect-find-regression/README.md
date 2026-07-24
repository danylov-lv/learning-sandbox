# 02 -- Bisect: Find the Regression

## Backstory

Someone reports that discounted prices are coming out wrong. Nobody knows
when it broke -- it's been "probably fine" for a while, and 14 commits
have landed since the pricing script was first written, most of them
unrelated cleanup, docs, and small features. You have one fact: it works
at the very first commit, and it's broken at the current tip. Somewhere
in between, exactly one commit is the culprit. Reading 14 diffs by eye is
possible; it's also exactly the kind of search a computer does better
than you do, provided you can turn "is this commit good or bad" into a
program.

## What's given

```bash
bash setup.sh
```

builds a scratch git repository at `work/` (gitignored, safe to blow away
and rebuild any time) with a **linear history of 14 commits on `main`**.
The repo has:

- `pricing.sh` -- a small bash library, most notably
  `price_after_discount PRICE DISCOUNT_PCT`, which is supposed to return
  the integer price after applying a percentage discount.
- `is_bad.sh` -- a self-contained test script, present from the very
  first commit and unchanged throughout the whole history. It sources
  `pricing.sh` and checks one known-correct case: `price_after_discount
  200 10` must equal `180`. It **exits 0 if that's true (good) and
  non-zero if it's false (bad)**.
- `README.md` -- unrelated project notes, changed by several commits.

Somewhere in the 14 commits, `price_after_discount`'s formula changed in
a way that breaks this check. Every commit before that point is good;
every commit at or after it is bad -- the badness doesn't come and go, so
a binary search is valid here. Don't read `pricing.sh`'s history by eye
to shortcut this -- the point of the task is running the search.

## What's required

1. Use `git bisect` (with `is_bad.sh` as the test) to find the **first
   commit where the regression is present** -- the earliest bad commit,
   with a good parent.
2. Write that commit's full 40-character SHA into `FIRST_BAD_SHA.txt` in
   this task directory (not inside `work/` -- that file is not part of
   the scratch repo, it's your answer sheet), replacing the placeholder
   line. Nothing else should be in the file besides the SHA on its own
   line.

`git bisect run bash is_bad.sh` will drive the whole search for you once
you've told it the known-good and known-bad endpoints -- you don't have
to manually check out and test each commit by hand, though you can if
you'd rather see each step.

## Completion criteria

Run, from this task directory:

```bash
uv run python tests/validate.py
```

It independently walks `work/`'s full commit history itself (checking out
each commit in order and running `is_bad.sh` against it, unrelated to
whatever bisect state you left behind), determines the true first-bad
commit, and compares it against what you wrote in `FIRST_BAD_SHA.txt`.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- `git bisect start` / `good` / `bad` / `run` / `reset`
- Binary search complexity -- why `git bisect` needs roughly
  `log2(N)` steps, not `N` steps, to find one bad commit among N
- Writing a good bisect test script: deterministic, fast, and testing
  exactly one thing
- `git bisect skip`, for when a commit in range can't be tested at all
  (not needed for this task, but worth knowing why it exists)

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
