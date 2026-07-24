# Commit History Policy

Fill in every section below. This is a policy for a real team working on
a real codebase (you can use this sandbox repo's own module structure as
the imagined codebase if that's easier than inventing one) -- write it as
something you would actually hold a teammate to, not as a survey of
options.

## Commit granularity and atomicity

[fill in -- what makes a commit "atomic" in your policy? What's the rule
for when a change that spans multiple files/layers is still one commit
versus when it must be split? Give at least one concrete example of a
change you'd split and one you'd deliberately keep together, and say why.]

## Commit message convention

[fill in -- subject line format and length limit, body content
expectations, whether/how you use a conventional-commits-style prefix
taxonomy (feat/fix/chore/refactor/...), imperative vs past tense, and
what a commit message must never look like (give a real bad example and
say specifically what's wrong with it).]

## Merge strategy: rebase vs merge vs squash

[fill in -- what strategy is used for landing a feature branch into your
main line, and why that one over the alternatives. State your policy on
rebasing a branch that other people have already pulled from. State
whether/when force-pushing is allowed at all.]

## Handling mistakes: amend, revert, and rewriting shared history

[fill in -- when is `git commit --amend` appropriate versus a new
commit? When do you `git revert` a bad commit instead of removing it from
history? What is the line between "history it's still fine to rewrite"
and "history that's now shared and must only be added to, never
rewritten"?]

## Bisectability and blame hygiene

[fill in -- what does your policy require so that `git bisect` and `git
blame` stay useful tools months later, not just at merge time? Cover both:
what makes a commit *bisectable* (does it leave the build/tests in a
working state on its own?), and what keeps `blame` output meaningful
(e.g. how large-scale reformatting/renaming commits are handled so they
don't bury real history).]

## Hostile review responses

Answer each question from `HOSTILE-REVIEW.md` in its own subsection
below. Answer from your policy's actual content above -- these should
read as applications of the policy you already wrote, not as new,
disconnected opinions.

### Q1

[fill in]

### Q2

[fill in]

### Q3

[fill in]

### Q4

[fill in]

### Q5

[fill in]

### Q6

[fill in]
