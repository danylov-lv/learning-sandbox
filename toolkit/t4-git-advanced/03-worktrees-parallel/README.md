# 03 -- Worktrees for Parallel Work

## Backstory

Two small, unrelated fixes need doing, and you'd rather not stash/switch/
stash/switch between branches every time you're interrupted, or waste
disk cloning the repo twice into two directories that then have to be
synced by hand. `git worktree` gives you multiple working directories
attached to the **same** `.git` (same object store, same refs, same
`git fetch` results, no duplication) each checked out to a different
branch at once. This is also the natural way to let an AI coding
assistant work on one branch in one worktree while you keep working in
another, without either of you touching the other's checkout -- see t1
for the AI-assisted side of that workflow.

## What's given

```bash
bash setup.sh
```

builds a scratch git repository at `work/` (gitignored, safe to blow away
and rebuild any time) with a **single commit on `main`**: one file,
`toolkit-notes.md`. That's the whole starting state -- the point of this
task is what you build from here with worktrees, not the seed content.

## What's required

All of the following happens **inside `work/`** (so the nested repo, and
everything under it, stays gitignored).

1. Create a worktree at `.worktrees/alpha`, on a **new** branch
   `feature/alpha`, based on `main`.
2. Inside that worktree, create a file `alpha-note.txt` containing
   exactly this one line:

   ```
   alpha worked on: parallel scraping fixes
   ```

   Commit it on `feature/alpha` with the exact commit message
   `Add alpha note`.

3. Create a second worktree at `.worktrees/beta`, on a **new** branch
   `feature/beta`, also based on `main`.
4. Inside that worktree, create a file `beta-note.txt` containing exactly
   this one line:

   ```
   beta worked on: retry backoff tuning
   ```

   Commit it on `feature/beta` with the exact commit message
   `Add beta note`.

5. `main` must stay exactly as `setup.sh` left it -- don't check it out
   and don't commit anything to it.
6. **Leave both worktrees in place** (don't `git worktree remove` them)
   -- the validator checks `git worktree list` as evidence you actually
   used the worktree mechanism, not just created two branches by hand.

The two branches are independent of each other -- do not merge one into
the other, and do not base `feature/beta` on `feature/alpha`.

## Completion criteria

Run, from this task directory:

```bash
uv run python tests/validate.py
```

It checks, against `work/`'s current state:

- `main`'s tip commit is unchanged from what `setup.sh` produced.
- `feature/alpha` exists, is exactly one commit ahead of `main`, that
  commit's message is `Add alpha note`, and its tree contains
  `alpha-note.txt` with the exact expected content (and nothing else
  different from `main`).
- `feature/beta` exists with the equivalent shape for `beta-note.txt` /
  `Add beta note`.
- `git worktree list` currently reports two worktrees rooted at
  `.worktrees/alpha` and `.worktrees/beta`, bound to `feature/alpha` and
  `feature/beta` respectively.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- `git worktree add` / `list` / `remove` and the linked-worktree model
  (one `.git` directory, multiple working trees, shared object store)
- Why you can't check the same branch out in two worktrees at once
- How worktrees interact with an AI coding assistant running in a
  separate working directory from your own editor/terminal
- `git worktree prune`, for when a worktree's directory was deleted by
  hand instead of via `git worktree remove`

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
