# t4 -- Git Advanced

Part of the **toolkit track**: small modules about using tools well,
rather than about an engineering topic. No docker, no database, no
capstone -- five single-evening tasks, each usable independently, going
beyond daily `add`/`commit`/`push` into the git mechanics that actually
save you (or cost you) time on a real team: rewriting history before it's
shared, finding a regression by search instead of by memory, working on
two things at once without duplicating a clone, recovering from a
deletion that looked permanent, and writing down a policy for all of the
above instead of relitigating it every time.

## Tasks

1. **[01-interactive-rebase-cleanup](01-interactive-rebase-cleanup/)** --
   turn a realistic messy branch (typo commit message, a stray debug
   commit, two `fixup!` commits) into a clean, linear, reviewable
   history via interactive rebase, without changing what the code does.
2. **[02-bisect-find-regression](02-bisect-find-regression/)** -- a
   14-commit history has one hidden commit that breaks a pricing
   calculation. Use `git bisect` with a provided test script to find it
   by binary search instead of by reading every diff.
3. **[03-worktrees-parallel](03-worktrees-parallel/)** -- use
   `git worktree` to work on two branches at once, in two working
   directories, off one `.git`. The natural pairing for running an AI
   coding assistant on one branch while you keep working on another --
   see t1 for the AI-assisted-engineering side of that workflow.
4. **[04-reflog-rescue](04-reflog-rescue/)** -- a branch with real,
   unmerged work got force-deleted. Recover the exact original commit
   object via `git reflog`, not by retyping the content from scratch.
5. **[05-history-design-writeup](05-history-design-writeup/)** -- a
   written task: draft a commit-granularity and history policy concrete
   enough to survive a hostile review, covering atomicity, message
   convention, merge strategy, and where the line is between history
   that's still fine to rewrite and history that isn't.

## How each task works

Tasks 01-04 are **repo-state tasks**: `bash setup.sh` builds a scratch
git repository at that task's own gitignored `work/` directory, already
in a specific starting state (messy, broken, or mid-disaster). You do the
real git operations yourself, directly against `work/`, using whatever
tools you'd normally use (a terminal, an editor's git integration, `git
rebase -i` at an actual editor). `uv run python tests/validate.py`
(from inside the task directory) then checks the **resulting state** of
`work/` -- commit graph shape, exact messages, tree/blob content,
branch pointers, recovered SHAs -- never *how* you got there. `setup.sh`
is safe to re-run any time you want to discard your progress and start
over; it always rebuilds `work/` from scratch, deterministically (fixed
author/committer dates and content, so the same commit SHAs come out on
every machine and every run).

Task 05 is a **written task**, same shape as module 17's design
exercises: fill in `POLICY.md` against a doc-gate validator (required
sections, grounding vocabulary, quantitative-or-concrete claims, and a
hostile-review gauntlet of `### Qn` questions from `HOSTILE-REVIEW.md`).

There are no reference solutions anywhere in this module -- not in
hints, not in `.authoring/`, not in the validators. Hints escalate in
three tiers (direction, mechanism, concrete-but-not-copy-pasteable), and
`.authoring/` documents the grading contract for whoever extends this
module later, not a worked answer.

## Setup

Each task is self-contained once you're in its directory:

```bash
cd toolkit/t4-git-advanced/01-interactive-rebase-cleanup
bash setup.sh
# ... do the git operation against work/ ...
uv run python tests/validate.py
```

`uv run` resolves against this module's `pyproject.toml` /
`uv.lock` regardless of which task directory you're standing in (uv
walks up to find them). No docker-compose, no services, no fixed ports
-- this module has neither, same as module 17.

## Off-limits

`.authoring/` documents this module's grading contract (intended final
repo states, the reasoning behind the SHAs and hardcoded values the
validators check against) -- it is not a solution file. Read it after
finishing a task, if at all, never before or during.
