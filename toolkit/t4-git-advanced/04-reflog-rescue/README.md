# 04 -- Reflog Rescue

## Backstory

"The branch is gone." Someone ran `git branch -D` on the wrong branch, or
force-deleted one that was never merged, or you did it yourself,
half-asleep, cleaning up branches after a long day. Two commits of design
work just vanished from `git branch --list` and `git log --all`. This is
the moment most people assume the work is gone -- it isn't, not yet. Git
doesn't delete commit objects the instant nothing points at them; they
sit in the object database, unreachable but intact, until garbage
collection eventually prunes them (by default, not for a long time). The
`reflog` -- a private, local, per-ref journal of "where did this ref
point, at each point in time" -- is usually enough to find your way back
to the exact commit, by SHA, before that happens.

## What's given

```bash
bash setup.sh
```

builds a scratch git repository at `work/` (gitignored, safe to blow away
and rebuild any time) already in the post-disaster state:

- `main` has 2 commits: an initial commit, then a later `update notes`
  commit made *after* the disaster below.
- A branch called `feature/valuable-work` was created off `main`,
  received two real commits revising a `payment-retry.md` design doc,
  was never merged into `main`, and was then deleted with
  `git branch -D feature/valuable-work`.

Run `git -C work branch --list` and `git -C work log --all --oneline`
yourself first -- confirm for yourself that the branch and its commits
are genuinely not visible through the normal ref-based views before you
start recovering anything.

## What's required

1. Find the two lost commits using `git reflog` (or an equivalent
   mechanism -- `git fsck --unreachable` also surfaces dangling commits,
   though without the descriptive context reflog entries carry).
2. Recreate the branch `feature/valuable-work`, pointing it at the exact
   original tip commit object (the "Switch retry design to exponential
   backoff" commit) -- not a new commit with matching content, the
   literal original commit object, still sitting in the object database.
3. Leave `main` exactly as it is -- don't merge the recovered branch into
   it, don't reset it, don't touch `notes.md` or `README.md` on `main`.

The whole point of this exercise is that recovery does not require
re-typing any content: the object with the exact original tree, message,
author, and parent already exists. Recovery is "find the SHA, point a
ref at it" -- if you find yourself re-creating `payment-retry.md` by hand
from scratch, you've missed the mechanism this task is teaching.

## Completion criteria

Run, from this task directory:

```bash
uv run python tests/validate.py
```

It checks, against `work/`'s current state:

- `feature/valuable-work` exists again.
- Its tip commit's SHA is exactly the original lost commit's SHA (proving
  you recovered the literal object, not a lookalike reconstruction).
- `main`'s tip is unchanged from what `setup.sh` produced.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- `git reflog` -- what it records (every ref update: commits, checkouts,
  resets, merges, rebases) and its default retention window
- The difference between "unreachable" and "gone" -- when git objects are
  actually removed (`git gc`, `expire`, `--prune`)
- `git fsck --unreachable` / `--dangling` as a reflog-independent way to
  find lost objects
- Why the reflog is local-only (never pushed, never fetched) and what
  that implies about recovering work that only ever existed on someone
  else's machine

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
