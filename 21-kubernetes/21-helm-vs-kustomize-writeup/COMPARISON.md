# Comparison: Helm vs Kustomize

## Mental models

[fill in: how Helm's templating model actually works mechanically --
Go `text/template` + Sprig functions rendering plain text from
`values.yaml`-driven inputs, which is only *afterward* parsed as YAML --
versus Kustomize's overlay model, where every layer (`bases`,
`overlays`/`components`) is already syntactically valid YAML, composed
by strategic-merge and JSON 6902 patches with no templating language
involved at all. State the actual mechanical difference between "render
text, then parse YAML" and "patch YAML, no text stage" -- not just "one
templates and one patches."]

## Where Helm wins

[fill in: concrete scenarios where Helm's model is the better fit --
packaging for reuse across teams or orgs, dependency management via
`Chart.yaml` `dependencies` and subcharts, lifecycle hooks
(pre-install/pre-upgrade/post-delete), consuming from a public chart
ecosystem. Ground each in a scenario, not a bullet list of features.]

## Where Kustomize wins

[fill in: concrete scenarios where Kustomize's model is the better fit --
no templating language to fight with, plain YAML that `kubectl diff` /
`kubectl apply -k` understands natively without a rendering step,
overlays that stay readable without running a tool first, GitOps
controllers that can show a real diff against the target live state.
Ground each in a scenario, not a bullet list of features.]

## Decision

[fill in: for one specific, stated scenario -- your own team's real
setup, or the 8-microservices/3-environments scenario from Q1 -- say
which tool you'd actually choose and why, including what you'd
concretely give up by not picking the other one. Pick one; "it depends"
without a stated resolution does not count.]

## Hostile review

[fill in: this section holds the answers to questions.md's Q1-Q5, each
as its own `### Qn` subsection below. Restating the question is not an
answer.]

### Q1

Your team ships 8 microservices to 3 environments (dev, staging, prod),
each environment differing in replica counts, a couple of env vars, and
which external DB host to point at. Lay out how you'd actually structure
this in Helm (chart-per-service? one umbrella chart? how many values
files?) and how you'd structure it in Kustomize (how many bases, how many
overlays, what lives in each). Then say which one you'd actually ship and
why -- not "it depends," pick one and defend it for this specific shape
of problem.

[fill in]

### Q2

A value must differ per environment (say, a feature-flag string) *and*
that same value needs to force a Deployment rollout whenever it changes,
via a checksum-style annotation on the pod template. Walk the exact
mechanism each tool uses to make that happen -- what actually computes
the hash, what actually carries it into the pod spec, and what happens if
a team forgets to wire it up in each case. Is one of these mechanisms
opt-in effort and the other closer to "you get it for free"?

[fill in]

### Q3

Under an Argo CD app-of-apps setup, which of the two composes better, and
specifically why -- think about what the `Application` CR's `source`
block looks like for each, what a `kubectl diff`/Argo CD diff view shows
a reviewer before a sync, and what changes about either setup the day you
add environment #4.

[fill in]

### Q4

Give one concrete thing Kustomize genuinely does better than Helm, and
one concrete thing Helm genuinely does better than Kustomize. Not in the
abstract -- name a specific scenario for each where picking the other
tool would visibly cost you something.

[fill in]

### Q5

Describe a real architecture where you'd deliberately use Helm *and*
Kustomize together in the same delivery pipeline, and explain why that's
not redundant -- what job is each one doing that the other one genuinely
can't (or can only do worse) in that architecture.

[fill in]
