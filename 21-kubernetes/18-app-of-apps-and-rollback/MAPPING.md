# Mapping: given/work-application.yaml

Map every field of `given/work-application.yaml` to what it actually does.
Write in your own words -- this is graded on whether you can explain the
mechanism, not on reproducing Argo CD's documentation.

## Identity and lifecycle

[fill in: `apiVersion`/`kind`; `metadata.name`/`metadata.namespace` (why
this must be `argocd` regardless of where the workload deploys);
`metadata.labels` vs `metadata.annotations` here -- what actually reads
each one; `spec.project` and what an `AppProject` (not shown, but named
here as `checkout-team`) constrains that `project: default` wouldn't.]

## Sources: single vs multi-source

[fill in: why this Application has `spec.sources` (plural) instead of
`spec.source` (singular), what each of the two entries in the list is for,
what `chart:` + `repoURL` pointing at a Helm repo means versus a plain git
`repoURL` + `targetRevision`, and what `ref: values` plus the `$values/`
prefix in `helm.valueFiles` actually wires together at render time.]

## Destination

[fill in: `spec.destination.name` vs `spec.destination.server` -- what
each one requires to already exist in this Argo CD installation, why a
platform team would prefer one over the other, and `spec.destination.namespace`.]

## Sync policy in depth

[fill in: `automated.prune`/`selfHeal`/`allowEmpty` each explained
separately; every entry under `syncOptions` (`CreateNamespace`,
`PrunePropagationPolicy=foreground`, `PruneLast`, `ApplyOutOfSyncOnly`,
`RespectIgnoreDifferences`) -- what each one changes about a sync that
would happen anyway without it; `retry.limit` and `retry.backoff`'s three
fields and how they combine into an actual retry schedule.]

## Ignore differences and drift

[fill in: what each of the three `ignoreDifferences` entries is telling
Argo CD to stop caring about, why each one exists (what would self-heal do
to that field without it), the difference between matching by
`jsonPointers` and matching by `managedFieldsManagers`, and why
`RespectIgnoreDifferences` (a syncOptions entry, not part of
`ignoreDifferences` itself) matters for these to actually hold during a
sync and not just during drift detection.]

## Sync waves, hooks, and finalizers

[fill in: what `argocd.argoproj.io/sync-wave: "1"` on *this Application's
own* metadata controls versus what the identical annotation controls when
it's on a plain resource inside a chart; what
`resources-finalizer.argocd.argoproj.io` in `metadata.finalizers` actually
does on `kubectl delete application ...`, and how it interacts with
`PrunePropagationPolicy=foreground`; `spec.revisionHistoryLimit` and
`spec.info` -- what each is for and what happens if you omit them.]

## Hostile-review responses

[fill in: this section holds the answers to questions.md's Q1-Q6, each as
its own `### Qn` subsection below. Restating the question is not an
answer.]

### Q1

`spec.syncPolicy.automated.selfHeal: true` is set, and so is an
`ignoreDifferences` entry for `checkout-api`'s `/spec/replicas`. An HPA
(not shown in this file, but real in prod) changes that Deployment's
`replicas` out from under Argo CD every few minutes. Someone on the team
also hand-edits `checkout-api`'s `image` tag directly with `kubectl edit`
during an incident. Walk through what self-heal does to each of these two
live edits, and explain precisely why `ignoreDifferences` produces two
completely different outcomes for them even though both are "someone
changed a live field Argo CD didn't put there."

[fill in]

### Q2

Trace exactly how a value inside `checkout-values.git`'s
`checkout/prod/values.yaml` ends up affecting what gets rendered from the
`checkout-umbrella` chart, given that they're two different entries under
`spec.sources`. What is the `ref: values` field doing, and what would go
wrong (name the actual failure, not just "it breaks") if the first
source's `helm.valueFiles` entries didn't start with `$values/`?

[fill in]

### Q3

`metadata.annotations` sets `argocd.argoproj.io/sync-wave: "1"` directly
on this Application object. If this Application were one of several
children applied by a parent app-of-apps Application (the pattern you
just built in `src/`), what would that annotation actually control? Now
contrast that with the very different thing the same
`argocd.argoproj.io/sync-wave` annotation controls when it's placed on a
plain Kubernetes resource (say, a ConfigMap) *inside* the chart this
Application deploys -- these are not the same ordering mechanism even
though they're the identical annotation key.

[fill in]

### Q4

`metadata.finalizers` lists `resources-finalizer.argocd.argoproj.io`, and
`syncPolicy.syncOptions` includes `PrunePropagationPolicy=foreground`.
Someone runs `kubectl delete application platform-checkout-prod -n
argocd`. Walk through what actually happens to the live `checkout`
namespace's resources, in what order, and say what would be different
(worse, in this team's case) if the finalizer were absent.

[fill in]

### Q5

`syncPolicy.retry` sets `limit: 5` with `backoff: {duration: 10s, factor:
2, maxDuration: 5m}`. The chart's rendered manifests currently fail to
apply every single time (a real, persistent error -- not a flake). Compute
the actual wait before each of the 5 retry attempts and say exactly when
Argo CD gives up and surfaces the sync as failed, being precise about
where `maxDuration` changes the naive doubling sequence.

[fill in]

### Q6

`spec.destination` here uses `name: prod-us-east` rather than `server:
https://...`. Explain what has to exist elsewhere in this Argo CD
installation for that to resolve to anything at all, and what happens --
concretely, not "it errors" -- if this Application also had a `server`
field set at the same time to a different, real API server URL.

[fill in]
