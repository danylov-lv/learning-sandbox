# Hint 2

For each `### Qn` in `## Hostile review`, the fastest way to end up with
an answer that's "mostly the question restated" is to answer in the
abstract. Instead, for every question, name the actual mechanism by the
tool's own vocabulary before you say anything evaluative:

- Q1 wants an actual layout: how many chart(s)/values files, or how many
  `bases`/`overlays`, not "you'd use values files for environments." Say
  what file lives where.
- Q2 wants you to trace what computes a hash and what carries it into
  the pod spec, for each tool, separately. If you can't name the specific
  field/annotation/generator suffix involved, you haven't traced it yet.
- Q3 wants you to describe what's actually sitting in an `Application`
  CR's `spec.source` block for each case, and what a reviewer looking at
  a pre-sync diff would see differently.
- Q4 and Q5 explicitly ask for a scenario, not a property. "Kustomize is
  simpler" is a property; "a 3-person team maintaining 2 overlays on one
  base doesn't want to learn a templating language for that" is a
  scenario.

Keep every answer's own claims checkable against something in
`README.md`'s "Topics to read up on" list -- if an answer can't be
grounded in one of those mechanisms, it's probably restating an opinion
rather than tracing one.
