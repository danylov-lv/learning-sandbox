# Hint 2

For commit granularity: a useful test for "should this be one commit or
several" is whether each candidate commit, checked out on its own, leaves
the system in a state that builds and passes its tests. A migration
commit that isn't yet used by any code, followed by a commit that starts
using it, usually passes that test as two commits. A rename that's
referenced in the same commit that depends on the new name usually has to
be one commit, or bisect lands on a broken intermediate state.

For merge strategy: rebase and merge-commit and squash-merge all answer
"how does a feature branch's history end up on main" differently, and
each trades something for something else -- squash-merge buys a clean
one-commit-per-PR main line but destroys any internal commit boundaries
the branch had; merge-commits preserve those boundaries but add merge
commits to the main line; rebase-and-fast-forward keeps a fully linear
main line but requires the branch to have been rebased onto main first,
which is exactly the operation that's dangerous once someone else has
pulled that branch.

For the message convention: think about what a message needs to answer
for someone doing `git blame` two years from now, who has zero context
you currently have in your head. "What" is visible in the diff already
-- the message's job is "why."

For bisect/blame hygiene specifically: a commit that's guaranteed to
build and test cleanly on its own is a commit `git bisect` can actually
use. A giant reformat-everything commit is fine for the build, but it's
exactly the kind of commit that makes `git blame` useless on every line
it touches -- there's a mechanism for telling `blame` to skip commits
like that.
