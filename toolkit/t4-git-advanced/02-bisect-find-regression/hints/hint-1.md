# Hint 1

You already have a pass/fail test (`is_bad.sh`) and two known endpoints
(the very first commit is good, the tip is bad). That's the entire input
`git bisect` needs -- it doesn't want you to read diffs, it wants a
program that answers "good or bad" for an arbitrary commit, and it'll
drive the checkout/test/repeat loop itself.

Don't manually `git checkout` each of the 14 commits in order -- that's
the linear search this exercise is specifically not asking for.
