# 17 — Drift, self-heal, and sync waves

## Backstory

At work, the templated `Application` you inherited from task 16's world
almost certainly has `syncPolicy.automated.selfHeal: true` set somewhere,
and nobody remembers who turned it on or why. Then one day someone
`kubectl edit`s a Deployment directly during an incident — bumps
replicas, patches an env var — and thirty seconds later it's back to
whatever git says it should be, with no warning, no Slack message,
nothing. If you don't know self-heal exists, that looks like the cluster
eating your emergency fix. Multi-resource apps have the same trap in the
other direction: a migration Job needs to finish before the new
Deployment starts serving traffic, and if nobody told Argo CD that via
sync waves and hooks, it'll happily apply everything at once and the app
will crash-loop against a schema that isn't there yet. This task makes
you turn both knobs on by hand, once, so you recognize the behavior
instead of getting surprised by it.

Arc 5 spans three tasks sharing task 16's Argo CD + Gitea install: 16 got
a first `Application` to `Synced`/`Healthy`; this one covers drift,
self-heal, and sync waves/hooks; 18 covers the app-of-apps pattern and
rollback.

## What's given

- Argo CD (**v3.4.5**) and an in-cluster Gitea, both already installed in
  namespace `argocd` by task 16's `scripts/install.sh`. This task does
  **not** install or reinstall either — if `uv run python tests/validate.py`
  reports they're missing, go run
  `16-argocd-app-by-hand/scripts/install.sh` first, then come back.
- `src/application.yaml` — a `# TODO(you): ...` stub for the Argo CD
  `Application`. You write this.
- `src/manifests/deployment.yaml`, `src/manifests/service.yaml`,
  `src/manifests/hook-job.yaml` — three more `# TODO(you): ...` stubs:
  the app the `Application` deploys. You write these too.
- The validator's own Gitea plumbing: unlike task 16 (where a fixture
  chart was pre-seeded), here **you** don't get direct write access to
  Gitea. `tests/validate.py` reads your `src/manifests/*.yaml` and pushes
  them, itself, into a fresh repo it owns
  (`sandbox20/t17-app.git` — a different repo from task 16's
  `platform-charts`, created on first run) before applying your
  `Application`. This is what makes "the annotations you wrote" gradable
  without you needing a Gitea login.

## What's required

Two things, both in `src/`:

**1. `src/application.yaml`** — an Argo CD `Application` with:

- `apiVersion: argoproj.io/v1alpha1`, `kind: Application`.
- `metadata.name: t17-app`, `metadata.namespace: argocd`.
- `spec.project: default`.
- `spec.source`:
  - `repoURL: http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/t17-app.git`
    — the exact in-cluster Service DNS name the validator pushes to.
    Same idea as task 16, different repo name.
  - `targetRevision: main`
  - `path: .`
- `spec.destination`:
  - `server: https://kubernetes.default.svc`
  - `namespace: t17`
- `spec.syncPolicy.automated` with **`selfHeal: true`** and **`prune:
  true`** — both required, checked literally as booleans. This is the
  actual point of the drift check below: an `Application` with a manual
  syncPolicy, or `automated` without `selfHeal`, will leave an
  out-of-band change sitting there `OutOfSync` forever — Argo CD only
  auto-corrects live drift when `selfHeal` is on.
  Add `syncOptions: [CreateNamespace=true]` too.

**2. `src/manifests/*.yaml`** — three Kubernetes resources, no
`metadata.namespace` on any of them (Argo CD injects `t17` from
`spec.destination.namespace` at sync time):

- A **Deployment** named `t17-workload`:
  - `metadata.labels["app.kubernetes.io/name"] = t17-workload`
  - `metadata.annotations["argocd.argoproj.io/sync-wave"] = "1"`
  - `spec.replicas` — any positive integer you choose (the validator
    reads it back to know what "reverted" means later).
  - a container using image `sandbox20-app:1.0` on port `8080`
    (`imagePullPolicy: IfNotPresent` — the image is already loaded into
    the kind cluster, no registry pull needed).
- A **Service** named `t17-workload`, same wave (`"1"`), selecting
  `app.kubernetes.io/name: t17-workload`, port `8080`.
- A **Job** named `t17-preflight` — the PreSync hook:
  - `metadata.labels["app.kubernetes.io/name"] = t17-hook`
  - `metadata.annotations["argocd.argoproj.io/hook"]` = `PreSync` (or
    `Sync`)
  - `metadata.annotations["argocd.argoproj.io/hook-delete-policy"]` set
    to one of `BeforeHookCreation` / `HookSucceeded` / `HookFailed` —
    without this, the *next* sync (including one triggered by self-heal)
    fails trying to create a Job whose name already exists.
  - `metadata.annotations["argocd.argoproj.io/sync-wave"] = "0"` — must
    run before the workload's wave `"1"`.
  - `spec.template.spec.restartPolicy: Never` (or `OnFailure`), some
    container that exits `0` quickly (e.g. `busybox:1.36` running a
    trivial `sh -c` command — already loaded in the kind cluster).

## The exact contract, and what the validator checks

1. Confirms Argo CD + Gitea are installed and Ready (points at task 16's
   install script if not).
2. Parses `src/manifests/*.yaml` directly and checks the fields above —
   names, labels, annotations, replica count, image — before anything
   touches the cluster (anti-cheat: a `Deployment` with the right name
   but the wrong wave, or a `Job` missing the hook annotation, fails
   here with a specific message).
3. Pushes those manifests into `sandbox20/t17-app.git` (force-push, so
   reruns always reflect your current files), applies your
   `src/application.yaml` into `argocd`, checks its spec fields directly
   (repoURL/destination/syncPolicy — same anti-cheat idea as task 16),
   nudges a sync, and waits (bounded) for `Synced`/`Healthy`.
4. Confirms the Deployment and Service actually landed, ready, in `t17`.
5. Checks the Application's own `status.operationState.syncResult.resources`
   for the hook Job's `hookPhase` — must be `Succeeded`, structural proof
   the PreSync hook actually ran (and finished) as part of the sync. If
   the Job is still around afterward (delete policy other than
   `HookSucceeded`), it also confirms the Job's completion timestamp is
   at or before the workload's earliest pod creation timestamp.
6. **The drift/self-heal check**: scales `deployment/t17-workload` to a
   different replica count out-of-band (`kubectl scale`, not through
   git), confirms that mutation actually landed, then waits (bounded,
   generous timeout) for it to revert back to your original replica
   count on its own. This only happens with `selfHeal: true` — a
   manual-sync or non-selfHeal `Application` will leave it drifted, and
   the wait times out with a clear message.

Your `Application` is deleted from `argocd` and namespace `t17` is
deleted at the end whether you pass or fail. The Gitea repo the
validator created (`sandbox20/t17-app`) is left in place — force-pushed
fresh on the next run, same idempotent convention as task 16's install
script. Argo CD and Gitea themselves are never touched.

## Completion criteria

From this task directory (after task 16's `scripts/install.sh` has been
run at least once):

```bash
uv run python tests/validate.py
```

## Estimated evenings

1–2

## Topics to read up on

- `spec.syncPolicy.automated`: `prune` vs. `selfHeal` — two independent
  switches (prune removes resources git no longer has; selfHeal corrects
  live resources that drifted from what git has), and why "automated"
  alone (without `selfHeal`) only auto-syncs on *git* changes, not on
  someone editing the live cluster.
- Drift detection: how the application controller continuously diffs
  live state against the desired manifest, and what triggers a
  self-heal reconciliation versus Argo CD's periodic background resync.
- Sync waves (`argocd.argoproj.io/sync-wave`): how resources within one
  sync are grouped and applied in ascending wave order, waiting for each
  wave to be healthy before the next starts.
- Resource hooks (`argocd.argoproj.io/hook`): `PreSync`, `Sync`,
  `PostSync` — what each phase means relative to the main apply, and how
  hooks interact with (but are ordered independently of) sync waves.
- Hook deletion policies (`argocd.argoproj.io/hook-delete-policy`):
  `BeforeHookCreation`, `HookSucceeded`, `HookFailed` — why a hook Job
  without one of these becomes a landmine on the second sync.
- `status.operationState.syncResult` on the `Application` CRD — where
  Argo CD records exactly what happened in the last sync operation,
  including per-resource hook phase, independent of whether that
  resource still exists live afterward.
