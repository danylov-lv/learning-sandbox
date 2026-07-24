# Hint 1

Four separate operations are needed here, and they're four different todo
verbs, not one clever trick: get rid of a commit entirely, merge two
commits into one (twice), and change a commit's message without touching
its content. Look at each commit in `git log --oneline` and decide, one
at a time, which of "keep as-is / merge into the previous real commit /
change only the message / delete" it needs -- before you open a rebase
todo list at all.

Also notice the naming: two commits are literally prefixed `fixup!`
followed by the exact subject line of an earlier commit. That prefix is
not decorative -- git has a specific rebase mode built around it.
