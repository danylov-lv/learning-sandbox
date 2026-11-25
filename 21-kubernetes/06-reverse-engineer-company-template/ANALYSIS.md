# Analysis: given/company-chart (svc-platform)

## How the template is organized

[fill in: what kind of chart this is (umbrella-style, single chart with a
`components` map, a subchart-per-service design, ...), what a
"component" is in this chart's vocabulary, and how a team would add a
new component to their release without touching a template file. Name
every file in `given/company-chart/templates/` and what it's responsible
for, in one pass, before going decision-by-decision in the next section.]

## Every decision explained

[fill in: walk every helper in `_helpers.tpl` (what it computes and why
it exists as a named template rather than being inlined everywhere it's
used) and every template file's job, one at a time. For each one, state
what would break or look wrong if that piece were deleted -- that's the
test for whether you actually understand why it's there versus just
describing what it renders. Cover: the naming helpers, the label
helpers, the image helper, the env-merging helper, the ConfigMap, the
Secret, the ServiceAccount/RBAC pair, the Deployment, the Service, and
the HPA.]

## Questionable decisions

[fill in: at least two decisions in this chart that you would push back
on in a design review, each with (a) what the chart actually does, (b)
the concrete failure mode it causes in production -- not "this is bad
practice" in the abstract, trace an actual incident it would cause --
and (c) the specific fix you'd propose, down to the field or template
line that changes.]

## What I would ask the platform team

[fill in: questions you'd bring back to whoever owns this chart --
things the chart doesn't tell you on its own (why a decision was made,
what happens in a scenario the chart doesn't seem to handle, what's
intentionally out of scope for this chart versus missing).]

## Hostile-review responses

[fill in: this section holds the answers to questions.md's Q1-Q6, each
as its own `### Qn` subsection below. Restating the question is not an
answer.]

### Q1

Someone edits `global.env.LOG_LEVEL` in git and Argo CD syncs the
change. Walk through exactly which pods restart and why. Now find one
config change in this same chart that a team would expect to cause a
restart but actually would not -- name the mechanism (or the missing
mechanism) that explains the difference.

[fill in]

### Q2

The `worker` component's `values.yaml` describes its liveness probe as
hitting `/health/deep`, "checks DB + queue connectivity" per the
comment. Trace the exact failure chain that turns "the database is
briefly degraded" into "every worker pod gets killed by the kubelet, and
none of them come back healthy until the database recovers on its own."
Why does this get worse, not better, as replica count goes up?

[fill in]

### Q3

A team ships two `helm upgrade` runs a week apart, from the same
`values-example.yaml`-style file with `api.image.tag` left unset both
times, and never bumps `Chart.yaml`'s `version` in between. Can the two
runs end up running different container images under the same tag?
Trace the mechanism through `_helpers.tpl`'s `svc-platform.image`
template, and say what its own comment claims happens versus what
actually happens.

[fill in]

### Q4

Every component's Deployment pulls from the same Secret name via
`envFrom`. The `api` component's on-call needs to rotate `DB_PASSWORD`
after a leak, so they edit `sharedSecret.data.DB_PASSWORD` and re-sync.
What happens to the `worker` component as a result, and does anyone
find out that it happened without going looking for it?

[fill in]

### Q5

`podAnnotations` values are rendered through Helm's `tpl` function
before being written into the pod template, rather than being copied in
as plain strings. What does that indirection actually buy a team
filling in this chart, and what would go wrong if a team's
`podAnnotations` value contained a template expression referencing a
field of `.Values` that doesn't exist for their component?

[fill in]

### Q6

Every component gets its own ServiceAccount and Role, scoped to
`get`/`list`/`watch` on Pods and ConfigMaps in its own namespace, instead
of one shared ServiceAccount for the whole release. What does the
per-component split actually buy you over the shared version? Now name
one thing about how Secrets are handled elsewhere in this chart that
undermines the "least privilege per component" story this RBAC section
is telling.

[fill in]
