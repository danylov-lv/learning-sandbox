# 01 -- Interactive Rebase Cleanup

## Backstory

You were heads-down on a small feature branch, moving fast: a couple of
real commits, one commit message you fat-fingered, a "just checking
something" debug commit you meant to drop before it ever got committed,
and two `fixup!` commits you made along the way (the way you actually
work when you notice a bug in something you committed five minutes ago --
commit the fix separately, squash it in later). Now it's time to open a
PR, and the history needs to read like you knew what you were doing the
whole time. Nobody wants to review "WIP debug" or figure out which of two
commits fixed the bug the other one introduced.

This is the single most common real-world use of interactive rebase: not
some dramatic history surgery, just turning "how it happened" into "what
it means," before anyone else has to read it.

## What's given

```bash
bash setup.sh
```

builds a scratch git repository at `work/` (gitignored, safe to blow away
and rebuild any time) with **8 commits on `main`**:

```
Initial commit
add threshold check              (bug: wrong comparison, fixed later)
Add pric alret logic              <- typo in the message, not the code
WIP debug                         <- stray debug commit, isolated to debug.log
fixup! add threshold check        <- fixes the bug from commit 2
add email notification channel
fixup! add email notification channel   <- fixes a bug from commit 6
update README
```

Two files: `price_alert.py` (a small toy module) and `README.md`. Run
`git -C work log --oneline` and `git -C work show <sha>` yourself to see
exactly what each commit changed before you touch anything.

## What's required

Turn the 8-commit history on `main` into a **5-commit linear history**
with exactly these commit messages, in this exact order (oldest to
newest):

1. `Initial commit`
2. `add threshold check`
3. `Add price alert logic` -- the typo from the original commit 3, fixed
4. `add email notification channel`
5. `update README`

Concretely, starting from the 8 commits above:

- **Drop** `WIP debug` entirely -- it should not exist anywhere in the
  final history, and `debug.log` must not exist in the final tree.
- **Squash** `fixup! add threshold check` into `add threshold check` --
  the fix becomes part of that commit; the fixup commit disappears as a
  separate entry. Keep `add threshold check`'s original message.
- **Squash** `fixup! add email notification channel` into
  `add email notification channel` the same way.
- **Reword** `Add pric alret logic` to `Add price alert logic`. Fix only
  the message -- the code that commit introduced must not change.
- Leave `Initial commit` and `update README` as they are.

The order above is also the order these five logical changes should end
up in on `main` -- which happens to be the order they're already in, so
you don't need to reorder anything to hit the target; the point of this
task is drop / squash / reword, done cleanly.

`git rebase -i` is inherently interactive, but nothing about grading here
requires a human at a keyboard: `GIT_SEQUENCE_EDITOR` lets you script the
todo-list edit, and `git rebase --autosquash` builds much of that
todo-list for you automatically from the `fixup!`-prefixed subjects.
Use whichever combination of rebase mechanics gets you to the target
state -- the validator only checks the *result*.

## Completion criteria

Run, from this task directory:

```bash
uv run python tests/validate.py
```

It checks, against `work/`'s current state:

- `main` has exactly 5 commits, is linear (every commit has exactly one
  parent, except the root), and the 5 messages match the target list
  above exactly, in order.
- No commit anywhere in `main`'s history still has a message starting
  with `fixup!` or `WIP`.
- `debug.log` does not exist in the final tree.
- `price_alert.py` and `README.md` in the final tree match the intended
  final content exactly -- so cleanup didn't accidentally change what the
  code does, only how the history reads.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- `git rebase -i` todo-list verbs: pick, reword, edit, squash, fixup, drop
- `git commit --fixup` / `git rebase --autosquash`
- `GIT_SEQUENCE_EDITOR` for scripting a normally-interactive rebase
- The difference between `squash` and `fixup` (commit message handling)
- Why rewriting history is safe on a branch nobody else has pulled, and
  why it stops being safe once they have

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
