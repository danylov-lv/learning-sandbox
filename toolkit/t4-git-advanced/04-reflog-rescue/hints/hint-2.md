# Hint 2

`git reflog show HEAD` (or just `git reflog`, same thing) lists every
commit `HEAD` has pointed at, most recent first, each with the operation
that put it there: `commit`, `checkout: moving from X to Y`, `reset`,
etc. While you were on `feature/valuable-work`, every commit you made
there updated `HEAD`'s reflog, and switching back to `main` added a
`checkout` entry too -- all before the branch was ever deleted.

Once you find the SHA of the commit you want back (the tip of the
deleted branch, not an intermediate one), a plain `git branch
<name> <sha>` recreates a branch pointing at that exact object -- no
different from creating a branch normally, except you're naming the
target commit by SHA instead of by an existing ref.
