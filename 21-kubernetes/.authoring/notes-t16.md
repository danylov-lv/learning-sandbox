# Authoring notes -- 16-argocd-app-by-hand

Owning task for **Argo CD + in-cluster Gitea** (cluster-global install,
`scripts/install.sh` + `uninstall.sh`). Both live in namespace `argocd`.
Tasks 17 and 18 assume both stay installed -- do not reinstall/uninstall
from those tasks.

## Versions pinned (verified live against this cluster, k8s v1.32.2)

- Argo CD **v3.4.5**, applied `--server-side --force-conflicts` from
  `https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.5/manifests/install.yaml`
  into namespace `argocd` (server-side apply for the same reason task 15
  uses it for CNPG: the Application/AppProject/ApplicationSet CRDs are
  large enough to blow past client-side apply's annotation-size limit).
  Waited Ready via `rollout status` on `deployment/argocd-server`,
  `deployment/argocd-repo-server`, and `statefulset/argocd-application-controller`
  (300s timeout each -- cold image pulls). Argo CD 3.4.x officially
  supports k8s 1.32-1.35.
- Gitea **gitea/gitea:1.24.7-rootless** (NOT the default rootful
  `gitea/gitea:1.24.7` tag -- see gotcha below), one Deployment + one
  Service (`gitea-http`, port 3000) + one PVC (`gitea-data`, 2Gi,
  `standard` StorageClass, mounted via `subPath` for both
  `/var/lib/gitea` and `/etc/gitea`), all in namespace `argocd`. sqlite3
  backend, `INSTALL_LOCK=true`, registration disabled.
- Manifests: `given/gitea/gitea.yaml` (Gitea) is applied directly by
  `scripts/install.sh`; the Argo CD manifest is pulled live from GitHub
  at install time (not vendored).

## Exact in-cluster contract (what tasks 17/18's authors should reuse)

- Seeded org: `sandbox20`, repo: `platform-charts`, default branch `main`,
  **public** (no credentials needed to clone/pull -- this is deliberate:
  Argo CD's `Application.spec.source` can point straight at a public repo
  with zero `Repository`/credentials Secret registration, which keeps this
  first task's contract simple; task 17/18 could introduce a private repo
  + credentials if that's ever wanted, but nothing here requires it).
- `repoURL: http://gitea-http.argocd.svc.cluster.local:3000/sandbox20/platform-charts.git`
  -- in-cluster Service DNS, resolvable only from inside the cluster
  (`argocd-repo-server` and any future consumer pod), NOT from the host.
- Chart lives at the **repo root** (`path: .`), pushed from this task's
  `given/chart/` (a small, complete, from-scratch chart -- NOT the
  learner's own Arc 2 chart; design.md's "push the Arc 2 chart" phrasing
  is satisfied in spirit -- a real, renderable Helm chart deploying
  `sandbox20-app` -- rather than literally reusing task 04/07's
  learner-authored chart, which would either be a stub or vary per
  learner and can't be committed as fixture material).
- Gitea admin: user `gitea-admin`, password `sandbox20-gitea-admin-pw`
  (hardcoded in `scripts/install.sh` -- fine, this is a throwaway lab git
  server, not a secret worth protecting). Gitea UI:
  `kubectl -n argocd port-forward svc/gitea-http 3000:3000`.
- Argo CD admin password: `kubectl -n argocd get secret
  argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d`.
  Argo CD UI: `kubectl -n argocd port-forward svc/argocd-server 8080:443`
  (self-signed cert).
- **Gotcha for 17/18 authors**: `argocd-initial-admin-secret` is only
  created once, on first install, and only while `argocd-secret`'s
  `admin.password` field is unset -- if you ever delete it to "regenerate
  a password", it will NOT come back on its own. To force a fresh one:
  `kubectl -n argocd patch secret argocd-secret --type=json -p='[{"op":"remove","path":"/data/admin.password"},{"op":"remove","path":"/data/admin.passwordMtime"}]'`
  then `kubectl -n argocd rollout restart deployment/argocd-server`. Hit
  this live during authoring (accidentally deleted the secret while
  testing) and confirmed the recovery path works.

## Gotcha: rootful Gitea image + non-root securityContext = CrashLoopBackOff

First attempt used the default `gitea/gitea:1.24.7` tag with Pod
`securityContext.runAsUser: 1000` (needed so `kubectl exec ... gitea admin
user create` -- which bypasses the image's own entrypoint and inherits the
container's raw UID -- runs as the same non-root user the server does,
instead of as root and getting "Gitea is not supposed to be run as root").
That tag's PID 1 is an s6-overlay supervisor that itself needs to start as
root to set up `.s6-svscan`; forcing non-root broke it
(`s6-svscan: fatal: unable to open .s6-svscan/lock: Permission denied`).
Fix: switch to the **`-rootless`** image variant, whose entrypoint IS the
gitea process (no s6), built to run as uid/gid 1000 from the start, with
data/config paths at `/var/lib/gitea` and `/etc/gitea` instead of `/data`.
Needed a PVC delete + recreate after switching (fsGroup chown only lands
cleanly on a fresh volume, not one with root-owned files from the earlier
crash-looping attempt).

## Task / grading

Learner writes `src/application.yaml` (an Argo CD `Application` CR),
`metadata.name: t16-app` in namespace `argocd`, pointed at the seeded repo
above, `spec.destination` at `https://kubernetes.default.svc` + namespace
`t16`, some `spec.syncPolicy`. Validator applies it, checks the spec
fields directly (anti-cheat on repoURL/path/destination), triggers a sync
by patching the Application's own `operation` field (the same trick
`argocd app sync` uses under the hood -- no `argocd` CLI dependency, no
API auth needed, works whether the learner's syncPolicy is automated or
manual), waits bounded for `status.sync.status == Synced` +
`status.health.status == Healthy`, then confirms a ready Deployment
(label `app.kubernetes.io/name=sandbox20-fixture`) actually landed in
`t16`. Deletes the Application + namespace `t16` at the end either way;
Argo CD + Gitea are never touched.

## Verified

Stock (unfilled `src/application.yaml` stub) fails cleanly:

```
NOT PASSED: kubectl apply -f src/application.yaml failed: error: no objects passed to apply (src/application.yaml is a TODO comment block that applies nothing until you replace it with a real Application)
```

exit 1, one line, no traceback.

Reference pass-path proven live: wrote a throwaway correct
`src/application.yaml` (sha256 of the stub recorded first), ran
`uv run python tests/validate.py` -- `PASSED: Application 't16-app'
reached sync.status=Synced, health.status=Healthy, and its chart landed a
ready workload in namespace 't16'` on the first try (fast: images already
`kind load`ed, chart is tiny). Reverted `src/application.yaml`
byte-identical -- sha256
`21b4a8d926f41bfd20e8c268ad3f1f404bee6e216059b90dc0619df4d0af4a2d`
matched before and after. Re-ran the validator against the reverted stub
afterward: same clean `NOT PASSED` line. No reference solution committed
anywhere.

`scripts/install.sh` re-ran three times total during authoring (fresh
install, once after deliberately breaking the admin secret, once more at
the end) -- fully idempotent each time, no errors, no duplicate
resources.

Final state left for 17/18: Argo CD (`argocd-server`,
`argocd-repo-server`, `argocd-applicationset-controller`,
`argocd-dex-server`, `argocd-notifications-controller`, `argocd-redis`
Deployments all 1/1, `argocd-application-controller` StatefulSet 1/1) +
Gitea (`gitea` Deployment 1/1) installed and Ready in namespace `argocd`;
no leftover `Application` objects; namespace `t16` does not exist.
