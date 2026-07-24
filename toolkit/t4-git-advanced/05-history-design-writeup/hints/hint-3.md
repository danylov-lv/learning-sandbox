# Hint 3

Concrete shape to work toward in each section:

- **Commit granularity and atomicity**: state the "builds and passes
  tests on its own" test explicitly, give one example that must be split
  under it and one that must NOT be split (a cross-cutting rename, or a
  hotfix where the layers can't be meaningfully separated), and say what
  you do when a change genuinely can't satisfy the test at every
  intermediate commit (this is Q1's scenario -- write the section so Q1
  is a direct application, not a new answer).
- **Commit message convention**: pin a subject-line length limit (a real
  number), pin whether/how you use a prefix taxonomy, state imperative
  mood explicitly, and give one concrete bad-message example plus what's
  wrong with it (feeds Q4 directly).
- **Merge strategy**: name the one strategy you actually use for landing
  PRs and why, then explicitly state your rule on rebasing an
  already-shared branch and on force-pushing -- with the actual mechanism
  (branch protection setting, convention, review gate) that backs the
  rule, not just the rule (feeds Q2 and Q3).
- **Handling mistakes**: draw the line explicitly -- "history is fine to
  rewrite until X, and from X onward only revert" -- where X is a concrete
  event (opened as a PR, merged to main, tagged as a release, whatever
  your team's boundary actually is).
- **Bisectability and blame hygiene**: state the same "builds on its own"
  requirement from the granularity section as what makes a commit
  bisectable, and name the specific mechanism for keeping large mechanical
  commits (reformatting, mass renames) from burying real blame history.
- **Hostile review responses**: once the five sections above are
  concrete, each `### Qn` answer should mostly be "per the X section
  above, here's what happens in this specific case" -- point back at your
  own rule and apply it, rather than reasoning from scratch each time.
