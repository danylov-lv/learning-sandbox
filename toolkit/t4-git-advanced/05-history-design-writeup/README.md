# 05 -- Meaningful History Design (Writeup)

## Backstory

Every task before this one asked you to fix a specific mess after the
fact: squash the fixups, find the regression, recover the deleted
branch. This one asks the question those tasks all assume an answer to:
what policy, followed from the start, makes those messes rare and makes
recovering from the ones that still happen easy? "Write good commits" is
not a policy -- it's not checkable, not teachable to a new hire, and
gives no answer when two reasonable engineers disagree about whether a
40-file hotfix should be one commit or five. A real policy has to survive
being read by someone looking for an excuse to ignore it.

This is a **written task**, like module 17's design exercises: no
scratch git repo, no service, no docker. The deliverable is a policy
document, graded structurally (required sections, grounding vocabulary,
concrete claims) plus a hostile-review gauntlet that checks whether your
policy actually resolves the situations it's supposed to resolve, not
just whether it uses the right words.

## What's given

- `POLICY.md` -- an unfilled template with every required `## ` section
  already in place as a `[fill in ...]` placeholder, including the
  `### Q1` .. `### Q6` hostile-review subsections.
- `HOSTILE-REVIEW.md` -- the six hostile-review questions in full;
  answer them inside `POLICY.md`, not here.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked, but it won't show you a solution.
- `hints/` -- three levels of hints, none containing a worked policy.

## What's required

Fill in every section of `POLICY.md`, including all six hostile-review
answers under `### Q1` .. `### Q6`. Write it as an actual policy you'd
hold a teammate to on a real codebase -- concrete rules and examples, not
a survey of "some teams do X, other teams do Y."

## Completion criteria

Run, from this task directory:

```bash
uv run python tests/validate.py
```

It checks, purely by structure and content shape (never by a human or
LLM judging "is this good design sense"):

- `POLICY.md`'s required `## ` sections are present, long enough, and
  free of leftover `[fill in ...]` markers.
- `POLICY.md` names enough of the concrete grounding vocabulary for this
  policy (atomic commits, bisectability, squash-merge, rebase,
  conventional commits, force-push, blame hygiene, and related terms).
- `POLICY.md` makes enough distinct quantitative-or-concrete claims (a
  line-count limit, a subject-line character limit, a number of retries,
  a specific taxonomy of prefixes) -- this is a policy with real rules in
  it, not just principles.
- All six `### Q1` .. `### Q6` hostile-review subsections are genuinely
  answered -- not missing, not a placeholder, not a verbatim copy of the
  question, and not too short.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Conventional Commits (the `feat`/`fix`/`chore`/`refactor`/... prefix
  taxonomy) and what it buys you downstream (changelog generation,
  semantic-version bumps)
- Atomic commits and why "does this leave the build/tests passing on its
  own" is a sharper test than "is this one logical change"
- Squash-merge vs merge-commit vs rebase-and-fast-forward as PR-landing
  strategies, and what each does to bisectability and blame
- The "never rewrite published history" rule, what "published" actually
  means in practice, and how branch protection enforces it instead of
  just asking nicely
- `git blame -w` / `-C` / `.git-blame-ignore-revs`, for keeping large
  reformatting commits from burying real history in blame output

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
