# Hint 3

Concrete shape to work toward, run from inside `work/`:

```
git reflog show HEAD
```

Look for the entries from when `HEAD` was on `feature/valuable-work` --
you're after the *last* commit made there before the `checkout: moving
from feature/valuable-work to main` entry, i.e. the tip, not the first
commit on that branch.

Once you have that SHA:

```
git branch feature/valuable-work <sha>
```

Confirm with `git log --oneline feature/valuable-work` that it shows both
of the original commits, and `git rev-parse feature/valuable-work` to
double check the SHA matches what you found in the reflog. `main` should
need no changes at all -- you never touch it in this task.
