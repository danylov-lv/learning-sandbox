# Hint 3

Concrete shape to work toward, run from inside `work/`:

1. Start the rebase from the root, with autosquash on:

   ```
   git rebase -i --autosquash --root main
   ```

   (or point `GIT_SEQUENCE_EDITOR` at a script first, then run the same
   command -- either way, autosquash rewrites the todo list *before*
   your editor/script ever sees it, so the two fixups already show up
   as `fixup` lines sitting right after their targets.)

2. In the todo list your editor receives, two more lines need changing:
   - The line for `WIP debug`: change its verb from `pick` to `drop`.
   - The line for `Add pric alret logic`: change its verb from `pick`
     to `reword`.

   A `GIT_SEQUENCE_EDITOR` script just needs to read the todo file,
   find those two lines by matching their commit subject text, rewrite
   the leading verb, and write the file back -- same mechanism you'd use
   for any scripted in-place file edit.

3. Because one line became `reword`, the rebase will pause once asking
   for a new commit message. If you scripted this, point `GIT_EDITOR`
   (or `git config core.editor`) at a second script that rewrites
   whatever `Add pric alret logic` text it finds in the message file to
   `Add price alert logic`, leaving everything else untouched.

4. When the rebase finishes, `git log --oneline` should show exactly 5
   commits with the 5 target messages, oldest to newest. Run the
   validator to confirm the tree matches too.

If you'd rather do this by hand at an actual editor instead of scripting
it, the exact same four decisions (drop / two fixups / reword) apply --
just make them interactively when the editor opens instead of via
environment variables.
