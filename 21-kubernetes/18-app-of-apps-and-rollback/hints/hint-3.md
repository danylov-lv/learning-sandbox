# Hint 3

For `MAPPING.md`: work through `given/work-application.yaml` top to
bottom once, in the six structural sections, *before* touching
`questions.md`'s hostile-review questions -- most of the six questions
are just a harder version of something you already had to explain in one
of those sections (Q1 needs the "sync policy in depth" +
"ignore differences" sections to already be straight in your head; Q3
needs "sync waves" to be straight; and so on). Writing the sections first
means you're not re-deriving the mechanism from scratch under a question.

For the questions specifically:

- Q1 and Q3 are both "same field/annotation, two different meanings
  depending on context" questions -- the trap in each is answering only
  one of the two contexts.
- Q2 and Q5 both want you to trace a concrete mechanism to its actual
  failure mode or actual numbers, not describe it in the abstract --
  "what breaks" and "compute the wait" both have one specific right
  answer, not a vibe.
- `kubectl explain application.spec --api-version=argoproj.io/v1alpha1
  --recursive` (works once Argo CD's CRD is installed, e.g. after task
  16) is a faster, more reliable reference for any field's exact shape
  than guessing from memory.

The validator rejects an answer that's mostly the question's own text
copied back (via `questions_path=` in `harness.common.check_answers`) --
if you're stuck, explain the mechanism in your own plain words first and
worry about polish second.
