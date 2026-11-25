# Hostile review questions

These are the questions a skeptical platform-team reviewer asks after you
present your Helm-vs-Kustomize position. Answer each one as `### Q1` ..
`### Q5` under the `## Hostile review` section of `COMPARISON.md`.
Restating the question is not an answer -- the validator rejects a
verbatim copy, and answers that are mostly padding around the question
text don't clear the bar either.

**Q1.** Your team ships 8 microservices to 3 environments (dev, staging,
prod), each environment differing in replica counts, a couple of env
vars, and which external DB host to point at. Lay out how you'd actually
structure this in Helm (chart-per-service? one umbrella chart? how many
values files?) and how you'd structure it in Kustomize (how many bases,
how many overlays, what lives in each). Then say which one you'd actually
ship and why -- not "it depends," pick one and defend it for this
specific shape of problem.

**Q2.** A value must differ per environment (say, a feature-flag string)
*and* that same value needs to force a Deployment rollout whenever it
changes, via a checksum-style annotation on the pod template. Walk the
exact mechanism each tool uses to make that happen -- what actually
computes the hash, what actually carries it into the pod spec, and what
happens if a team forgets to wire it up in each case. Is one of these
mechanisms opt-in effort and the other closer to "you get it for free"?

**Q3.** Under an Argo CD app-of-apps setup, which of the two composes
better, and specifically why -- think about what the `Application` CR's
`source` block looks like for each, what a `kubectl diff`/Argo CD diff
view shows a reviewer before a sync, and what changes about either setup
the day you add environment #4.

**Q4.** Give one concrete thing Kustomize genuinely does better than
Helm, and one concrete thing Helm genuinely does better than Kustomize.
Not in the abstract -- name a specific scenario for each where picking
the other tool would visibly cost you something.

**Q5.** Describe a real architecture where you'd deliberately use Helm
*and* Kustomize together in the same delivery pipeline, and explain why
that's not redundant -- what job is each one doing that the other one
genuinely can't (or can only do worse) in that architecture.
