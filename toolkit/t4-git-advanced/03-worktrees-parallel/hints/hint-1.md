# Hint 1

You need two working directories that are both attached to the same
`.git`, each checked out to its own new branch, so you can have both
branches "open" (as actual files on disk, not just as refs) at the same
time. That's a different tool than `git checkout -b` -- checkout only
ever has one branch active at a time in a given working directory.
