# Hint 1

`git branch -D` deletes a ref (the branch pointer). It does not delete
the commit objects that ref used to point at, and it does not delete the
record of what your `HEAD` was pointing at while you were working on that
branch. There is a log of that, kept locally, that survives a branch
deletion.
