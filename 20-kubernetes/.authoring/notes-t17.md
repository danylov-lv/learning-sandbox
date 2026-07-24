# Authoring notes -- 17-drift-selfheal-waves

Builds on task 16's Argo CD (v3.4.5) + in-cluster Gitea, both already
installed in namespace `argocd`. This task installs nothing itself --
`_require_argocd_and_gitea()` in `tests/validate.py` checks
`argocd-server`/`argocd-repo-server` Deployments,
`argocd-application-controller` StatefulSet, and `gitea` Deployment are
all ready, and points at `16-argocd-app-by-hand/scripts/install.sh` with
a clear message if not.

## Design decision: validator pushes the learner's manifests to Gitea

Task 16 seeded a fixed fixture chart the learner's `Application` points
at. Here the learner's *manifests themselves* (wave/hook annotations)
are the graded artifact, and they need to come from git for Argo CD to
apply hooks/waves correctly (hooks are a sync-time concept, not
meaningful via a bare `kubectl apply`). Rather than giving the learner
Gitea write credentials (out of scope, extra moving part), the validator
reads `src/manifests/*.yaml` directly (anti-cheat field checks happen
here, on the parsed YAML, before anything touches the cluster), then
pushes those exact files into a fresh repo it owns:
`sandbox20/t17-app.git` -- a distinct repo name from task 16's
`platform-charts`, under the same `sandbox20` org (org already exists
from task 16's install, reused; never touched task 16's repo itself).
Push mechanism mirrors task 16's `install.sh`: port-forward
`svc/gitea-http:3000` in `argocd` (via `harness.common.port_forward`),
create the repo via Gitea's REST API if `GET .../repos/sandbox20/t17-app`
404s, then `git init` a temp dir, copy the manifest files in flat (no
subdirectory -- `Application.spec.source.path: .` at repo root), commit,
`git push -f` over the port-forwarded address using the same throwaway
admin creds documented in notes-t16.md
(`gitea-admin` / `sandbox20-gitea-admin-pw`). Force-push every run keeps
it idempotent and always reflects the learner's current files (same
convention task 16's install script already established).

## Design decision: fixed resource names/labels, not a label-selector-only contract

Task 16 let the learner name their chart's resources freely (found via
label selector only). Here the validator needs to `kubectl scale` a
*specific* Deployment for the drift test and read a *specific* Job's
hook phase, so `src/manifests/*.yaml` must produce exactly:
`Deployment/t17-workload`, `Service/t17-workload`, `Job/t17-preflight`
(each also carrying `app.kubernetes.io/name` labels, but the fixed name
is what the validator actually keys off of -- simpler and less ambiguous
than requiring a label selector to resolve to exactly one match).

## Design decision: hook-delete-policy is a required field, not optional

Caught this live while first drafting the validator's drift check: Argo
CD's self-heal, when it detects drift on the Deployment, doesn't do a
narrow "patch just that field" -- it triggers a full sync operation,
which re-runs the PreSync hook. If the hook Job has no
`argocd.argoproj.io/hook-delete-policy`, the completed Job from the
*first* sync is still sitting there, and the self-heal-triggered sync's
attempt to create a new Job with the same name fails outright, which can
block the whole sync (including the Deployment fix the drift check is
waiting on). Confirmed this by testing without a delete policy first
during authoring -- the self-heal wait timed out because the re-sync
kept failing on the stale Job, not because self-heal itself wasn't
working. Made `hook-delete-policy` a required, validated annotation
(any of `BeforeHookCreation`/`HookSucceeded`/`HookFailed` accepted) once
this was diagnosed, and documented the "why" prominently in
README/hints since it's a genuinely non-obvious gotcha, not busywork.

## Design decision: hook ordering checked via Application status, not the live Job

`argocd.argoproj.io/hook-delete-policy: HookSucceeded` (a perfectly
valid, common choice) deletes the Job right after it succeeds -- so a
validator that only looks at the live Job in `t17` would sometimes find
nothing there at all, even on a fully correct submission. Instead,
`_check_hook_ordering()` reads
`status.operationState.syncResult.resources[]` off the `Application`
itself: each entry for a hook resource carries `hookType` and
`hookPhase` (`Running`/`Succeeded`/`Failed`), recorded by Argo CD
regardless of what happens to the resource afterward. Checked
`hookPhase == "Succeeded"` for the `Job`/`t17-preflight` entry -- this is
present and correct for every hook-delete-policy choice, verified live
for `BeforeHookCreation` (kept the reference Job around this run).
As a bonus, *if* the Job is still live (delete policy other than
`HookSucceeded`), the check also compares `job.status.completionTime`
against the earliest pod `creationTimestamp` under the Deployment's
label selector -- structural, no wall-clock threshold, just a relative
before/after assertion, skipped gracefully if the Job's already gone.

## Drift/self-heal check: what was actually verified live

`_check_drift_selfheal()`: after Synced/Healthy, reads the learner's
chosen replica count from the already-parsed manifest (no live re-read
needed), `kubectl scale deployment/t17-workload --replicas=<N+3> -n t17`
out-of-band, confirms the scale actually landed (bounded 20s wait --
guards against a false pass if the scale command itself silently
failed), then waits (bounded 150s, 3s interval) for `.spec.replicas` to
return to `N` on its own.

Timing observed live, reference run (replicas 2 -> drifted to 5 ->
reverted): landed back at 2 replicas well within the 150s budget --
Argo CD's application controller reacts to live drift fast (informer-
driven watch, not waiting for the ~3-minute default background resync),
typically within single-digit seconds in this cluster. 150s is a
generous, documented ceiling, not a tuned number -- consistent with the
repo's "no absolute wall-clock gates" rule (it's a bounded wait, not a
"must finish in N seconds" performance assertion).

**Non-vacuousness, proven live, not just assumed**: manually applied an
`Application` with `syncPolicy.automated.selfHeal: false` (everything
else identical -- same repo, same manifests, already pushed from the
reference run) directly via `kubectl` (bypassing the validator's own
static `selfHeal must be true` spec check, to isolate and test the
*runtime* behavior specifically), synced it to Healthy, then scaled the
Deployment to 5 replicas out-of-band and polled for 60s straight:
`sync.status` stayed `OutOfSync` and `spec.replicas` stayed at `5` the
entire time -- no reversion. Confirms the drift check is not trivially
satisfied by "any Application, any syncPolicy" -- it genuinely requires
`selfHeal: true` to pass, matching the design brief's "a manual-sync
Application would NOT self-revert" requirement. Cleaned up that manual
`Application`/namespace immediately after.

## Wave/hook manifest contract (final)

- `Job/t17-preflight`: `argocd.argoproj.io/hook: PreSync` (Sync also
  accepted), `argocd.argoproj.io/hook-delete-policy` (any valid value),
  `argocd.argoproj.io/sync-wave: "0"`, `restartPolicy: Never|OnFailure`.
  Reference used `busybox:1.36` (already `kind load`ed) running
  `sh -c "echo preflight ok"` -- trivial, deterministic, no flakiness.
- `Deployment/t17-workload` + `Service/t17-workload`: both
  `argocd.argoproj.io/sync-wave: "1"`, both labeled
  `app.kubernetes.io/name: t17-workload`. Deployment uses
  `sandbox20-app:1.0` (already `kind load`ed), port 8080,
  `imagePullPolicy: IfNotPresent`.
- No `metadata.namespace` on any of the three -- Argo CD injects `t17`
  from `spec.destination.namespace` (confirmed this is still the
  behavior for plain-manifest, non-Helm sources, same as task 16's
  chart templates never hardcoding namespace).

## Verified live

Stock (unfilled stubs) fails cleanly, first check hit (before any
cluster mutation beyond the pre-existing `_require_argocd_and_gitea`
read-only checks):

```
NOT PASSED: no Deployment named 't17-workload' found in src/manifests/*.yaml -- src/manifests/ only contains TODO comment stubs until you replace them with real resources
```

exit 1, one line, no traceback.

sha256 of all four stub files recorded before writing a throwaway
reference solution in place:

```
80eb6f1bca2412e8372e28405ec3697b10c4b7b5fe5f223cdeae8fbdb5c6e490  src/application.yaml
2b253d69ecfe39396cfacaacdce9f17d1f37c871f6ceb562015438b2f4a55c05  src/manifests/deployment.yaml
c7cbba98775140a762b4bc165524b3f0693eb3e81484f24bb38e7dc8796041da  src/manifests/service.yaml
0e38817a3dff434178cdf33a8a68e586b077e695acb626fee13f40ae268ccb95  src/manifests/hook-job.yaml
```

Reference pass-path run:

```
PASSED: Application 't17-app' synced with correct wave/hook ordering, and self-healed an out-of-band drift back to 2 replicas
```

-- on the first try. Reverted all four files byte-identical afterward;
sha256 matched exactly against the table above. Re-ran the validator
against the reverted stubs -- identical clean `NOT PASSED` line as
before. No reference solution committed anywhere in the task directory,
hints, or these notes (the YAML shown above only ever existed
transiently on disk during this authoring session, then reverted).

## Cleanup

Final state left for the next session: `argocd` namespace has no
`Application` objects, `t17` namespace does not exist, Gitea repo
`sandbox20/t17-app` (created by this validator during testing) was
deleted via the Gitea API (`DELETE /api/v1/repos/sandbox20/t17-app` ->
204, confirmed gone with a follow-up 404). Argo CD (`argocd-server`,
`argocd-repo-server`, `argocd-applicationset-controller`,
`argocd-dex-server`, `argocd-notifications-controller`, `argocd-redis`
Deployments, `argocd-application-controller` StatefulSet) and Gitea
(`gitea` Deployment) left installed and Ready in `argocd`, untouched
otherwise -- task 18 can build on the same install.

## Gotchas worth flagging for a future session (or task 18's author)

- Argo CD's self-heal reacting to drift also means it will re-run
  PreSync hooks on every self-heal cycle, not just the first sync --
  this is *why* the hook-delete-policy requirement exists at all, and is
  worth remembering if task 18's app-of-apps pattern also uses hooks
  anywhere in its child Applications.
- `argocd.argoproj.io/sync-wave` values are always annotation strings
  even though they look numeric (`"1"`, not `1`) -- same gotcha class as
  `selfHeal: true` needing to be a real YAML boolean, not a quoted
  string; both are easy first-pass mistakes and both are checked
  explicitly by the validator with a specific error message rather than
  a generic YAML-shape failure.
