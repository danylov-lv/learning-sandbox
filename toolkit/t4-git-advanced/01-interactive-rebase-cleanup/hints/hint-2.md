# Hint 2

`git rebase -i --autosquash <base>` scans the todo list for `fixup!
<subject>` / `squash! <subject>` commits and automatically reorders them
directly beneath the commit whose subject they match, with the right verb
already applied. That handles both fixups in one flag -- you don't need
to move any lines by hand for those two.

What's left after autosquash does its part: one commit needs `drop`
instead of `pick`, and one needs `reword` instead of `pick`. You can edit
those two lines yourself in the todo list, interactively or not.

For a non-interactive edit of the todo list, `GIT_SEQUENCE_EDITOR` is an
environment variable pointing at any executable that receives the
todo-list file path as its argument and can rewrite it in place --
`git rebase` runs it instead of opening your normal editor. The `reword`
verb then pauses the rebase again for a commit-message edit, which is
`GIT_EDITOR` (or `core.editor`) doing the same trick for the `COMMIT_EDITMSG`
file.

Find the earliest commit you need to rebase from (`--root`, since the
very first commit is untouched but still part of the sequence you're
reordering around).
