# Hint 2

`argocd.argoproj.io/sync-wave` and `argocd.argoproj.io/hook` are
answering two different questions, and it's easy to conflate them:

- **Sync wave** answers "in what order, relative to each other, do
  *normal* resources in this sync get applied?" Lower numbers first;
  Argo CD waits for each wave to be healthy before starting the next.
  It's a plain annotation on any resource — a Deployment, a Service, a
  ConfigMap, anything.
- **Hook** answers "does this resource run as a one-shot task at a
  specific *phase* of the sync (PreSync/Sync/PostSync), instead of being
  a normal reconciled resource at all?" A `PreSync` hook Job always
  finishes before the Sync phase's resources get applied, regardless of
  what wave number you put on it — waves and hooks are independent
  axes, which is exactly why this task asks for annotations from both.

The validator checks exact string values (annotation values are always
strings in Kubernetes, even when they look like numbers —
`argocd.argoproj.io/sync-wave: "1"`, quoted, not `1`), and it checks
`selfHeal` as a literal YAML boolean (`true`), not the string `"true"`.

For the hook Job specifically: without a
`argocd.argoproj.io/hook-delete-policy` annotation, a completed hook Job
just sits there. The *next* time Argo CD tries to sync this
`Application` — which happens automatically the moment your out-of-band
drift triggers self-heal — it tries to create a new Job with the same
name and fails, because the old one (already `Completed`) is still
there. That failed re-sync can then block the self-heal from ever
reaching your Deployment. Pick a delete policy.

Once your `src/manifests/*.yaml` and `src/application.yaml` both apply
cleanly and the validator reports `Synced`/`Healthy`, look at
`kubectl --context kind-sandbox20 -n argocd get application t17-app -o
yaml` under `status.operationState.syncResult.resources` — that's
exactly where the validator reads the hook Job's `hookPhase` from, and
it's a good way to see what "the sync actually ran your hook" looks
like from Argo CD's own side.
