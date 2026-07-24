# Hostile review questions

These are the questions a skeptical platform-team reviewer asks when you
present your read of `given/company-chart`. Answer each one as `### Q1` ..
`### Q6` under the `## Hostile-review responses` section of `ANALYSIS.md`.
Restating the question is not an answer -- the validator rejects a
verbatim copy, and answers that are mostly padding around the question
text don't clear the bar either.

**Q1.** Someone edits `global.env.LOG_LEVEL` in git and Argo CD syncs the
change. Walk through exactly which pods restart and why. Now find one
config change in this same chart that a team would expect to cause a
restart but actually would not -- name the mechanism (or the missing
mechanism) that explains the difference.

**Q2.** The `worker` component's `values.yaml` describes its liveness
probe as hitting `/health/deep`, "checks DB + queue connectivity" per the
comment. Trace the exact failure chain that turns "the database is
briefly degraded" into "every worker pod gets killed by the kubelet, and
none of them come back healthy until the database recovers on its own."
Why does this get worse, not better, as replica count goes up?

**Q3.** A team ships two `helm upgrade` runs a week apart, from the same
`values-example.yaml`-style file with `api.image.tag` left unset both
times, and never bumps `Chart.yaml`'s `version` in between. Can the two
runs end up running different container images under the same tag?
Trace the mechanism through `_helpers.tpl`'s `svc-platform.image`
template, and say what its own comment claims happens versus what
actually happens.

**Q4.** Every component's Deployment pulls from the same Secret name via
`envFrom`. The `api` component's on-call needs to rotate `DB_PASSWORD`
after a leak, so they edit `sharedSecret.data.DB_PASSWORD` and re-sync.
What happens to the `worker` component as a result, and does anyone
find out that it happened without going looking for it?

**Q5.** `podAnnotations` values are rendered through Helm's `tpl`
function before being written into the pod template, rather than being
copied in as plain strings. What does that indirection actually buy a
team filling in this chart, and what would go wrong if a team's
`podAnnotations` value contained a template expression referencing a
field of `.Values` that doesn't exist for their component?

**Q6.** Every component gets its own ServiceAccount and Role, scoped to
`get`/`list`/`watch` on Pods and ConfigMaps in its own namespace, instead
of one shared ServiceAccount for the whole release. What does the
per-component split actually buy you over the shared version? Now name
one thing about how Secrets are handled elsewhere in this chart that
undermines the "least privilege per component" story this RBAC section
is telling.
