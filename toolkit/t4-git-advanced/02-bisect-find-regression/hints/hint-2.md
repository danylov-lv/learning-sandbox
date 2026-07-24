# Hint 2

The workflow has three phases: tell bisect the two endpoints, let it
automate the search, read off the answer.

- `git bisect start`, then mark the current tip and the first commit
  (oldest in `git log --reverse`) as the two endpoints it needs.
- `git bisect run <command>` repeatedly checks out a candidate commit and
  runs `<command>` there, using the command's exit code (0 = good,
  nonzero = bad) to narrow the range automatically, continuing until only
  one candidate is left.
- `is_bad.sh` is already written to behave exactly like a bisect test
  script wants: it exits 0 or nonzero based on whether the pricing
  function is correct at whatever commit happens to be checked out.
- When it's done, bisect tells you directly which commit it landed on --
  no need to compute anything yourself. `git bisect log` also shows the
  full trail if you want to double check it.

Don't forget to leave the bisect session (there's a command for that) once
you have your answer, so `work/` ends up back on a normal branch instead
of a detached bisect state.
