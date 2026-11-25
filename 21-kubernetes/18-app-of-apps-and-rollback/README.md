# 18 — App-of-apps and rollback

## Backstory

Arc 5's first task had you hand-write one `Application`. Task 17 covered
drift, self-heal, and sync waves. At a real platform team, though, nobody
`kubectl apply`s Applications one at a time — a whole environment's worth
of them is itself checked into git, and one root `Application` points at
that directory, so "onboard a new service" is a PR, not a page someone
runs by hand. This task has you build exactly that (the "app of apps"
pattern), then use it as the excuse to practice the other half of GitOps
nobody skips in a real incident: rolling a bad change back with `git
revert`, not `kubectl edit`, so the fix lives in history instead of
evaporating on the next sync. Finally, you'll sit down with a realistic
umbrella-style `Application` a platform team actually ships and map every
field on it to what it does — which, once you look closely, is itself an
app-of-apps child. Recognizing that shape on sight is the point.

Arc 5 shares one Argo CD + Gitea install across tasks 16-18 (see task 16's
README if you skipped straight here — this task assumes both are already
up).

## What's given

- Argo CD (v3.4.5) and Gitea, installed by task 16 and still running in
  namespace `argocd`. This task does **not** reinstall either — if
  `uv run python tests/validate_cp1.py` fails complaining Argo CD or
  Gitea isn't installed, go run
  `16-argocd-app-by-hand/scripts/install.sh` first (from that task's
  directory), then come back.
- `given/child-chart/` — a small fixture Helm chart (deploys
  `sandbox20-app:1.0`). The validator pushes it into a **new** Gitea repo,
  `sandbox20/t18-child-chart.git`, for your two child Applications
  (checkpoint 1) to deploy. Not yours to edit.
- `given/workload-chart/` — a second, independent copy of the same kind of
  chart, pushed into its own new repo, `sandbox20/t18-workload.git`. This
  one is the target of checkpoint 2's rollback exercise; keeping it
  separate from the chart above means cp1 and cp2 never interfere with
  each other's git history.
- `given/workload-app.yaml` — the Argo CD `Application` for checkpoint 2,
  applied by `tests/validate_cp2.py` itself. You don't write an
  Application for cp2; you write git commands against the repo it tracks.
- `given/work-application.yaml` — a realistic "work" Argo CD `Application`
  for checkpoint 3's mapping exercise. Not deployed anywhere (it points at
  a fictional cluster/Helm repo) — you're reading it, not applying it.
- `src/root-app.yaml`, `src/apps/app-a.yaml`, `src/apps/app-b.yaml` — `#
  TODO(you): ...` stubs. These are the only manifests you write.
- `questions.md` — the six hostile-review questions for checkpoint 3,
  answered inside `MAPPING.md`.
- `MAPPING.md` — the written deliverable for checkpoint 3, an unfilled
  `[fill in]` template.
- `NOTES.md` — free-form, ungraded scratch space.

## What's required

### Checkpoint 1 — app of apps

Write a **parent** Application in `src/root-app.yaml` whose `spec.source`
is a directory of *other Application manifests*, not a Helm chart:

- `metadata.name: t18-root`, `metadata.namespace: argocd`.
- `spec.source.repoURL` pointing at
  `http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/t18-apps.git`
  (the validator creates this repo and pushes your `src/apps/*.yaml`
  files into its root every run), `path: .`, `targetRevision: main`.
- `spec.destination.server: https://kubernetes.default.svc`,
  `spec.destination.namespace: argocd` — this is important and easy to
  get backwards: the parent's own output is a set of `Application`
  *objects*, and `Application` objects only mean anything to Argo CD when
  they live in its own namespace. `t18` is where the eventual *workloads*
  end up — that's the children's destination, not this one's.
- `spec.syncPolicy` set (automated is simplest).

Then write **two** child Applications, `src/apps/app-a.yaml` (name
`t18-child-a`) and `src/apps/app-b.yaml` (name `t18-child-b`), each:

- `metadata.namespace: argocd`.
- `spec.source.repoURL` pointing at
  `http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/t18-child-chart.git`,
  `path: .`, `targetRevision: main`.
- `spec.destination.namespace: t18` (this one really does deploy into
  `t18` — it's a plain chart, not another layer of Applications).
- `spec.syncPolicy` set.

You never push these files to Gitea yourself — the validator reads
`src/apps/*.yaml` off disk and pushes them for you every run. You also
never `kubectl apply` the children directly; the validator only applies
`src/root-app.yaml`, and checks that the two children showed up *because
Argo CD reconciled the parent*, not because anything else created them.

### Checkpoint 2 — git revert rollback

No YAML to write. Run `uv run python tests/validate_cp2.py` once — first
run seeds `sandbox20/t18-workload.git` with a known-good commit (image
`sandbox20-app:1.0`) and then a **bad** commit on top that flips the image
tag to a version that was never built, breaking the live workload on
purpose, and fails with `NOT PASSED` telling you the bad commit's sha.
That failure is expected; it's an instruction, not a bug report.

Then do the actual exercise, using the Gitea admin credentials from task
16 (`gitea-admin` / `sandbox20-gitea-admin-pw`):

```bash
# from anywhere, with a port-forward to Gitea running in another terminal:
kubectl --context kind-sandbox20 -n argocd port-forward svc/gitea-http 3000:3000

git clone http://gitea-admin:sandbox20-gitea-admin-pw@127.0.0.1:3000/sandbox20/t18-workload.git
cd t18-workload
git log --oneline          # see the bad commit the validator printed
git revert <bad-sha>        # keep the default "Revert ..." / "This reverts commit ..." message
git push
```

Re-run `uv run python tests/validate_cp2.py` — it checks the **live git
history** of the repo (not a file you fill in): the tip of `main` must
actually be a revert of the marked bad commit, then waits for Argo CD to
resync and confirms the live workload is back on `sandbox20-app:1.0` and
Healthy. A fresh clone with no revert pushed will not pass this — there is
no shortcut around actually doing it.

### Checkpoint 3 — mapping + re-verification

Fill in `MAPPING.md`:

- Six structural sections walking every field of
  `given/work-application.yaml`: identity/lifecycle, sources (including
  the multi-source `ref:` mechanism), destination, sync policy in depth,
  ignore-differences/drift, and sync-waves/hooks/finalizers.
- A `## Hostile-review responses` section with `### Q1` .. `### Q6`
  answering `questions.md`'s six questions in your own words — restating
  a question, or mostly padding around its text, does not count as
  answering it.

`tests/validate_cp3.py` also re-runs `validate_cp1.py` and
`validate_cp2.py` as real subprocesses and requires both to still pass —
do cp3 last, once 1 and 2 are already green.

## Exact contract

| Object | Name | Namespace | Notes |
|---|---|---|---|
| Parent Application | `t18-root` | `argocd` | source: `sandbox20/t18-apps.git` |
| Child Application | `t18-child-a` | `argocd` | source: `sandbox20/t18-child-chart.git`, destination `t18` |
| Child Application | `t18-child-b` | `argocd` | source: `sandbox20/t18-child-chart.git`, destination `t18` |
| Rollback Application | `t18-workload-app` | `argocd` | validator-managed, source: `sandbox20/t18-workload.git`, destination `t18` |

Gitea repos this task creates (all new, all under the existing
`sandbox20` org, all separate from task 16's `platform-charts`):
`t18-apps`, `t18-child-chart`, `t18-workload`.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py   # run it twice -- see "Checkpoint 2" above
uv run python tests/validate_cp3.py
```

cp1 deletes its own Applications (`t18-root` + both children, cascade) at
the end whether it passes or fails, but does not delete namespace `t18`
(cp2 shares it). cp2 leaves `t18-workload-app` running. Argo CD and Gitea
themselves are never touched by any of the three.

When you're completely done with this task, you can clean up by hand:

```bash
kubectl --context kind-sandbox20 -n argocd delete application t18-root t18-child-a t18-child-b t18-workload-app --ignore-not-found
kubectl --context kind-sandbox20 delete namespace t18 --ignore-not-found
```

(Gitea repos `t18-apps`/`t18-child-chart`/`t18-workload` are harmless to
leave around — they cost nothing and don't affect any other task.)

## Estimated evenings

2

## Topics to read up on

- The app-of-apps pattern: one Application whose source is a directory of
  other Application manifests, and why its own `spec.destination` has to
  be the Argo CD namespace, not wherever the eventual workloads land.
- Declarative rollback via git: `git revert` (creates a new commit undoing
  a change, preserving history) versus `git reset`/force-push (rewrites
  history) — why GitOps tooling and teammates both strongly prefer the
  former, and what breaks about the latter on a shared branch.
- Argo CD `spec.sources` (plural) and multi-source apps: a Helm chart
  source plus a separate values-only git source via `ref:`.
- `ignoreDifferences` and how it interacts with `selfHeal` — telling Argo
  CD to stop fighting a field some other controller (an HPA, a mutating
  webhook) legitimately owns.
- `resources-finalizer.argocd.argoproj.io` and cascading delete — what
  happens to an Application's managed resources when the Application
  object itself is deleted, with and without the finalizer.
- `argocd.argoproj.io/sync-wave` — the same annotation key means a
  different ordering depending on whether it's on a child Application
  inside an app-of-apps parent, or on a plain resource inside one
  Application's own sync.
