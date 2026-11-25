# 16 — Argo CD, demystified: an Application by hand

## Backstory

At work, "deploying" probably means merging a PR and watching a Slack
bot report green — some GitOps controller (almost certainly Argo CD)
notices the git repo changed, diffs it against the live cluster, and
reconciles the difference. That controller, and the `Application`
object that tells it what to sync from where, is usually already set up
by a platform team by the time you touch it. This task opens the box:
you install Argo CD yourself, stand up a small git server for it to pull
from, and hand-write the one `Application` resource that turns "a chart
sitting in a repo" into "a running workload," so the next time a
templated Application shows up in a PR at work, you know exactly what
every field in it is doing.

Arc 5 spans three tasks sharing this same Argo CD + Gitea install:
this one gets a first `Application` to `Synced`/`Healthy`; 17 covers
drift, self-heal, and sync waves; 18 covers the app-of-apps pattern and
rollback. Everything you install here stays installed for both.

## What's given

- `scripts/install.sh` — a **cluster-global** install (see
  `.authoring/design.md`'s "Cluster-global installs" table if you're
  curious about the module-wide convention): installs Argo CD
  (**v3.4.5**) into namespace `argocd`, and an in-cluster Gitea git
  server (**gitea/gitea:1.24.7-rootless**) alongside it in that same
  namespace. It then seeds Gitea with an organization, a repository, and
  pushes a small, complete, working Helm chart into it (`given/chart/`
  — not something you write; it's fixture material, packaging the
  familiar `sandbox20-app`). Run it once:

  ```bash
  bash scripts/install.sh
  ```

  It's idempotent — safe to re-run if it fails partway or you just want
  to confirm everything's still there. It prints the Argo CD admin
  password and how to reach both UIs at the end; you don't need either
  UI to pass this task, but they're useful for poking around.

  Argo CD and Gitea stay installed for the rest of the module once this
  runs — task 17 and 18 assume both are already there and won't
  reinstall them. Don't run `scripts/uninstall.sh` unless you
  specifically want them gone.

- `given/chart/` — the seeded fixture chart, for reference (you can
  `helm template given/chart` locally to see exactly what it renders).
  It deploys one Deployment + one Service for `sandbox20-app:1.0`.
  Nothing here is yours to edit — the install script already pushed a
  copy of it into Gitea; this local copy just lets you see what your
  `Application` is pointing at.

- `src/application.yaml` — a `# TODO(you): ...` stub. This is the only
  file you write.

## What's required

Write an Argo CD `Application` in `src/application.yaml`. The exact
contract:

- `apiVersion: argoproj.io/v1alpha1`, `kind: Application`.
- `metadata.name: t16-app`, `metadata.namespace: argocd` (Argo CD's own
  API server/controller only watch `Application` objects living in its
  own namespace by default).
- `spec.project: default` (the out-of-the-box `AppProject` every fresh
  Argo CD install ships with).
- `spec.source`:
  - `repoURL: http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/platform-charts.git`
    — the exact in-cluster Service DNS name + org/repo the install
    script seeded. This is **not** reachable from your own machine's
    browser (it's a `svc.cluster.local` name, only resolvable inside the
    cluster) — that's fine, it only needs to resolve for Argo CD's own
    `repo-server` pod, which lives in the same namespace.
  - `targetRevision: main`
  - `path: .` — the chart sits at the repo root, not in a subdirectory.
- `spec.destination`:
  - `server: https://kubernetes.default.svc` — the in-cluster API
    server. This task deploys into the same cluster Argo CD itself runs
    on, not some external one.
  - `namespace: t16`
- `spec.syncPolicy` — must be present. `automated: {prune: true,
  selfHeal: true}` is the simplest choice and what the hints assume;
  add `syncOptions: [CreateNamespace=true]` too (or create the namespace
  yourself first — the validator creates `t16` itself either way, so
  this is really about the field being wired correctly, not about which
  namespace ends up existing).

## Completion criteria

From this task directory (after `scripts/install.sh` has been run once,
either by you or already by a previous session):

```bash
uv run python tests/validate.py
```

The validator:

1. Confirms Argo CD (`argocd-server`, `argocd-repo-server`,
   `argocd-application-controller`) and Gitea are installed and Ready
   (clear message pointing at `scripts/install.sh` if not).
2. Confirms the seeded Gitea repo is reachable in-cluster and actually
   contains `Chart.yaml`.
3. Applies `src/application.yaml` into namespace `argocd` and inspects
   the resulting `Application` object's own spec directly —
   `repoURL`/`path` must actually point at the seeded in-cluster Gitea
   repo (anti-cheat: pointing at some other, e.g. public GitHub, chart
   fails here even if that chart is perfectly valid), and
   `destination.server`/`destination.namespace` must be the in-cluster
   API server + `t16`.
4. Nudges Argo CD to sync (the same mechanism `argocd app sync` uses
   under the hood) and waits, bounded, for `status.sync.status ==
   Synced` and `status.health.status == Healthy`.
5. Confirms the chart's Deployment actually landed a ready replica in
   namespace `t16` — not just that Argo CD *claims* Synced/Healthy.

Your `Application` is deleted from `argocd` and namespace `t16` is
deleted at the end whether you pass or fail. Argo CD and Gitea
themselves are left installed either way.

## Estimated evenings

1

## Topics to read up on

- The GitOps model in general: git as the single source of truth for
  desired state, a controller continuously reconciling live state
  towards it, versus the older "push" model of `helm upgrade`/`kubectl
  apply` run from a CI pipeline or someone's laptop.
- The Argo CD `Application` CRD specifically: `spec.source` (repo +
  revision + path, and how it differs once you get to `spec.sources`,
  plural, for multi-source apps in later tasks), `spec.destination`
  (cluster + namespace), `spec.project`, `spec.syncPolicy`.
- `sync` status vs. `health` status — two independent axes.
  `sync.status` answers "does live state match git?"; `health.status`
  answers "is what's running actually working?" (a Deployment can be
  perfectly in-sync with git and still be `Degraded` if its pods are
  crash-looping). A learner mixing these up is a common first
  misunderstanding.
- Manual vs. automated sync (`spec.syncPolicy.automated`), and briefly
  what `prune`/`selfHeal` each control — full depth on self-heal and
  drift is task 17's job, not this one's.
- Self-managed (`servers: https://kubernetes.default.svc`, Argo CD
  deploying into its own cluster) vs. external clusters registered via
  `argocd cluster add` — why a from-scratch lab always starts with the
  former.
- Argo CD's own component split: `argocd-server` (API/UI/auth),
  `argocd-repo-server` (clones git repos, renders manifests/Helm/
  Kustomize), `argocd-application-controller` (the actual reconciliation
  loop, diffing live vs. desired and driving `sync`/`health`) — and why
  it's three separate deployments/statefulset rather than one process.
