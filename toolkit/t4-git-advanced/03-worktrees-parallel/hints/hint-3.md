# Hint 3

Concrete shape to work toward, run from inside `work/`:

```
git worktree add .worktrees/alpha -b feature/alpha
git worktree add .worktrees/beta  -b feature/beta
```

Then, in each worktree, write the exact file content the README
specifies and commit it there -- either by `cd`-ing into the worktree
directory or by using `git -C .worktrees/alpha <command>` /
`git -C .worktrees/beta <command>` from wherever you are:

```
printf '%s\n' "<exact alpha line>" > .worktrees/alpha/alpha-note.txt
git -C .worktrees/alpha add alpha-note.txt
git -C .worktrees/alpha commit -m "Add alpha note"
```

(and the equivalent for beta). Don't `git worktree remove` either one
afterward -- the validator checks that `git worktree list` still shows
them. Finish with `git worktree list` yourself to confirm both are there
and bound to the right branches before running the validator.
