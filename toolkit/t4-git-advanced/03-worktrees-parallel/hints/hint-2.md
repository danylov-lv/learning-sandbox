# Hint 2

`git worktree add <path> -b <new-branch>` does two things at once: creates
`<new-branch>` (based on whatever's currently checked out where you run
the command, i.e. `main`) and checks it out into a brand-new working
directory at `<path>`, fully independent of your original working
directory from that point on.

Run each `git worktree add` from inside `work/` so the new branch is
based on `work/`'s `main`, and give it a relative path under
`.worktrees/` so the new directory lands inside `work/` (and therefore
stays covered by the module's `.gitignore`, same as `work/` itself).

Once a worktree exists, it behaves like any other working directory: `cd`
into it (or pass `git -C <path> ...`) and `add`/`commit` normally on
whatever branch it has checked out.

`git worktree list` shows every linked worktree and which branch each one
currently has checked out -- useful both while you work and as a sanity
check before you consider the task done.
