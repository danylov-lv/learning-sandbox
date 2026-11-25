# Hostile review questions

These are the questions a skeptical platform-team reviewer asks after you
present your read of `given/work-application.yaml`. Answer each one as
`### Q1` .. `### Q6` under the `## Hostile-review responses` section of
`MAPPING.md`. Restating the question is not an answer -- the validator
rejects a verbatim copy, and answers that are mostly padding around the
question text don't clear the bar either.

**Q1.** `spec.syncPolicy.automated.selfHeal: true` is set, and so is an
`ignoreDifferences` entry for `checkout-api`'s `/spec/replicas`. An HPA
(not shown in this file, but real in prod) changes that Deployment's
`replicas` out from under Argo CD every few minutes. Someone on the team
also hand-edits `checkout-api`'s `image` tag directly with `kubectl edit`
during an incident. Walk through what self-heal does to each of these two
live edits, and explain precisely why `ignoreDifferences` produces two
completely different outcomes for them even though both are "someone
changed a live field Argo CD didn't put there."

**Q2.** Trace exactly how a value inside
`checkout-values.git`'s `checkout/prod/values.yaml` ends up affecting what
gets rendered from the `checkout-umbrella` chart, given that they're two
different entries under `spec.sources`. What is the `ref: values` field
doing, and what would go wrong (name the actual failure, not just "it
breaks") if the first source's `helm.valueFiles` entries didn't start with
`$values/`?

**Q3.** `metadata.annotations` sets `argocd.argoproj.io/sync-wave: "1"`
directly on this Application object. If this Application were one of
several children applied by a parent app-of-apps Application (the pattern
you just built in `src/`), what would that annotation actually control?
Now contrast that with the very different thing the same
`argocd.argoproj.io/sync-wave` annotation controls when it's placed on a
plain Kubernetes resource (say, a ConfigMap) *inside* the chart this
Application deploys -- these are not the same ordering mechanism even
though they're the identical annotation key.

**Q4.** `metadata.finalizers` lists
`resources-finalizer.argocd.argoproj.io`, and `syncPolicy.syncOptions`
includes `PrunePropagationPolicy=foreground`. Someone runs `kubectl delete
application platform-checkout-prod -n argocd`. Walk through what actually
happens to the live `checkout` namespace's resources, in what order, and
say what would be different (worse, in this team's case) if the finalizer
were absent.

**Q5.** `syncPolicy.retry` sets `limit: 5` with `backoff: {duration: 10s,
factor: 2, maxDuration: 5m}`. The chart's rendered manifests currently fail
to apply every single time (a real, persistent error -- not a flake).
Compute the actual wait before each of the 5 retry attempts and say
exactly when Argo CD gives up and surfaces the sync as failed, being
precise about where `maxDuration` changes the naive doubling sequence.

**Q6.** `spec.destination` here uses `name: prod-us-east` rather than
`server: https://...`. Explain what has to exist elsewhere in this Argo CD
installation for that to resolve to anything at all, and what happens --
concretely, not "it errors" -- if this Application also had a `server`
field set at the same time to a different, real API server URL.
