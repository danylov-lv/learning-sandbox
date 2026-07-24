# Hint 3

Concrete shape to work toward, run from inside `work/`:

```
git bisect start
git bisect bad main
git bisect good <sha-of-the-first-commit>
git bisect run bash is_bad.sh
```

(`git log --format=%H --reverse main | head -1` gets you that first SHA
without reading through the whole log by eye.)

`git bisect run` will print a line like `<sha> is the first bad commit`
once it finishes -- that SHA is your answer. Copy the full 40-character
form (not the abbreviated one shown in the "Bisecting: ..." progress
lines) into `FIRST_BAD_SHA.txt` in the task directory.

Finish with `git bisect reset` to return `work/` to `main` and clear the
bisect state before running the validator.
