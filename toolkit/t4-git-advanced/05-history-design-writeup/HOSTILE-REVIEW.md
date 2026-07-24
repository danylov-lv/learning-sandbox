# Hostile review -- 05-history-design-writeup

Answer every question below inside `POLICY.md`, under the matching
`### Q1` .. `### Q6` subsection in its "Hostile review responses"
section. Answer from your own policy's actual content -- a generic
answer that could apply to any team's policy, or a restatement of the
question, does not count as answered.

### Q1

Your policy says commits should be atomic and revertible. A production
incident forces a hotfix that touches 40 files across three layers
(schema migration, API, frontend) because the bug genuinely required all
three to change together to not be broken in between. Do you block that
PR on commit-granularity grounds, split it into multiple commits that
would each leave the system broken if reverted individually, or let the
40-file commit through as a deliberate exception? What does your policy
actually say happens here, concretely -- not "use judgment."

### Q2

You mandate squash-merge on pull requests, for a clean single-commit-per-
PR main-line history. A teammate argues this destroys bisectability
*inside* a PR that happened to fix three unrelated bugs in one branch,
because `git bisect` can no longer land on which of the three fixes was
which. Who's right under your policy, and what does your policy actually
require about PR scope that would prevent this situation from recurring
-- not just how you'd clean up after it happens?

### Q3

Someone force-pushed a rebase onto a branch that two teammates had
already pulled and built local commits on top of, and both of their
local histories broke. Does your policy allow rebasing a branch once
anyone else has pulled it? If yes, under what conditions, and what is the
teammate supposed to do to recover -- if no, what's the actual mechanism
(branch protection, a named convention, something else) that would have
stopped this from being possible in the first place, not just discouraged?

### Q4

Six months from now, someone runs `git bisect` on a hard-to-reproduce bug
and lands on a commit whose message is `fix stuff`. Whose failure is that
under your policy -- the author's, the reviewer's, or a process gap -- and
what specific, checkable rule in your commit-message convention would
have caught this message before merge, as opposed to a style preference
that nobody enforces?

### Q5

A PR both fixes a null-pointer bug and is only possible because it
includes a refactor that exposed the bug in the first place (the bug was
latent and unreachable before the refactor). Under your conventional-
commit taxonomy, does this land as `fix`, `refactor`, or something else,
and does your policy actually give a rule for this case or does it just
gesture at "use good judgment"? If a rule, state it; if judgment, say so
plainly and explain why a rule isn't possible here.

### Q6

A junior engineer asks why they can't just commit `wip`, `wip2`, `still
broken`, `ok now it works` forty times locally and squash them into one
commit right before opening the PR. Give the concrete, technical reason
your policy would give for why this specific workflow is fine, not fine,
or fine-with-a-caveat -- not a vague appeal to "clean history is good
practice."
