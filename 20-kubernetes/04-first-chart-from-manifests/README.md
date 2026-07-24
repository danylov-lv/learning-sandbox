# 04 — First chart from manifests

## Backstory

At work you fill in `values.yaml` for a chart someone else designed and
move on. This task flips that: you're the one designing it. Take the raw
`Deployment`/`Service`/`ConfigMap`/`Secret` you hand-wrote in Arc 1 (tasks
01-03) and grow them into a real Helm chart, written from scratch.

"From scratch" is deliberate. `helm create` dumps a scaffold full of
opinions this task doesn't need (`serviceAccount`, `ingress`,
`autoscaling`, a `NOTES.txt` referencing none of your resources) and it is
extremely tempting to keep 90% of it unread and just edit the parts that
obviously need editing. That gets you a chart that works without you
understanding why any of it is shaped the way it is — which is exactly the
gap this arc exists to close. Read a `helm create` scaffold's
`_helpers.tpl` for reference if you want (`helm create /tmp/scratch-ref`
somewhere outside this repo), but write every file in `chart/` yourself.

## What's given

`chart/` ships as a skeleton, not a blank directory:

- `chart/Chart.yaml` — already valid (`apiVersion: v2`, `name: worker`,
  `version: 0.1.0`). Leave it as-is unless you have a specific reason to
  bump the version.
- `chart/values.yaml`, `chart/values-dev.yaml`, `chart/values-prod.yaml`,
  and every file under `chart/templates/` — `# TODO(you): ...` stub
  comment blocks describing what belongs in each file. None of them render
  into working resources yet. `helm template t04-worker chart/` against
  the stock chart produces zero resources; that's expected, and is exactly
  where the validator is designed to fail first — cleanly, not with a
  YAML parse error.
- `given/review-checklist.md` — a self-review checklist for your
  `values.yaml` design decisions (what should be a value vs. hardcoded,
  naming, defaults safety, docs). Not graded by the validator. Go through
  it yourself once your chart passes before you consider this task done —
  it's the review a teammate would actually give the PR.

## What's required

Fill in `chart/values.yaml`, every file under `chart/templates/`, and
write `chart/values-dev.yaml` / `chart/values-prod.yaml` yourself, so that
the chart satisfies this contract exactly:

**`chart/templates/_helpers.tpl`**

- `worker.fullname` — a release-name-prefixed resource name, truncated to
  63 characters, following the standard pattern (see hints if the shape
  isn't familiar).
- `worker.labels` — a standard label block every resource applies,
  including at minimum `app.kubernetes.io/name`,
  `app.kubernetes.io/instance`, and `helm.sh/chart`.

Every resource in this chart must be named via `include "worker.fullname" .`
and labeled via `include "worker.labels" .` (or a selector-only subset
where a resource specifically needs one — see the Service/selector note
below).

**`chart/values.yaml`** — exact key paths:

| Key | Meaning |
|---|---|
| `image.repository` | default `sandbox20-app` |
| `image.tag` | default `"1.0"` |
| `image.pullPolicy` | default `IfNotPresent` |
| `replicaCount` | integer |
| `service.port` | Service port (container always listens on `8080`) |
| `config.greeting` | rendered into a ConfigMap; consumed as container env `CONFIG_GREETING` via `configMapKeyRef` |
| `resources` | empty (`{}`) by default; passed through to the container's `resources:` field as-is |
| `extraEnv` | a map; rendered into the container's `env:` list with `range`, one entry per key |
| `secret.enabled` | bool; when `true`, render a `Secret` plus an `APP_SECRET_TOKEN` container env var sourced from it via `secretKeyRef`; when `false`, render neither |
| `secret.token` | the Secret's value when `secret.enabled` is `true` |

The Deployment's `REQUIRED_ENV` env var must list exactly the env vars
actually wired for the current values — `CONFIG_GREETING` always,
`APP_SECRET_TOKEN` only when `secret.enabled` is `true`. Hardcoding both
names unconditionally makes the app crash-loop the moment `secret.enabled`
is `false` (see `app/app.py`'s `check_required_env`).

**`chart/templates/deployment.yaml`** additionally needs a
`checksum/config` annotation on the pod template, hashing the rendered
`ConfigMap`'s contents — so a `config.greeting` change alone forces a
rollout on the next `helm upgrade`, the same pattern behind every
"my ConfigMap change didn't roll the pods" incident you'll debug at work.

**`chart/values-dev.yaml`** — `replicaCount: 1`, no `resources` set,
`secret.enabled: false`.

**`chart/values-prod.yaml`** — `replicaCount: 3`, `resources` set (real
requests/limits), `secret.enabled: true`. Do not commit a real
`secret.token` here — it's supplied at install/upgrade time via `--set`.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator, roughly in this order:

1. `helm lint chart/` passes.
2. `helm template t04-worker chart/` (bare defaults) parses as multi-doc
   YAML and every resource is named with the fullname helper (prefixed by
   the release name `t04-worker`) and carries the labels helper's required
   keys, with `app.kubernetes.io/instance` equal to the release name.
3. `CONFIG_GREETING` is wired via `configMapKeyRef` (a literal value fails
   this even if the app happens to start), and `REQUIRED_ENV` always
   includes `CONFIG_GREETING`.
4. The Deployment's pod template carries a non-empty `checksum/config`
   annotation, and that annotation's value **changes** when re-rendered
   with `--set config.greeting=<something else>`.
5. `--set replicaCount=4` renders `spec.replicas: 4` (proves
   `.Values` wiring, not a hardcoded replica count).
6. `--set extraEnv.APP_FOO=bar` renders an `APP_FOO=bar` container env
   entry.
7. `-f chart/values-dev.yaml` renders `replicas: 1` and **no** `Secret`
   document.
8. `-f chart/values-prod.yaml` renders `replicas: 3`, a non-empty
   container `resources` block, a `Secret` document, and `APP_SECRET_TOKEN`
   wired via `secretKeyRef` into that Secret.
9. `REQUIRED_ENV` is checked to actually adapt: it must not list
   `APP_SECRET_TOKEN` under the dev values and must list it under the prod
   values.
10. **Live**: `helm install t04-worker chart/ -n t04 --create-namespace -f
   chart/values-dev.yaml`, wait for rollout, port-forward the Service —
   `GET /` returns `200`, and `GET /env?name=CONFIG_GREETING` echoes the
   value actually stored in the live ConfigMap (not a value the validator
   assumes in advance). Then `helm upgrade` onto `chart/values-prod.yaml`
   plus `--set secret.token=...`, wait for rollout, and assert 3 ready
   replicas. Finally `helm uninstall` and delete namespace `t04` —
   whether the task passed or failed.

If the validator tells you the cluster isn't up, run `bash
scripts/cluster-up.sh` from `20-kubernetes/` first.

## Estimated evenings

1

## Topics to read up on

- `_helpers.tpl` and `include`/`define` — why chart-wide naming/labeling
  logic belongs in one place instead of being copy-pasted per template.
- The standard `<chart>.fullname` pattern and why it special-cases a
  release name that already contains the chart name.
- Kubernetes' recommended label set
  (`app.kubernetes.io/name`/`instance`/`managed-by`, `helm.sh/chart`) and
  why `spec.selector` on a Deployment is immutable — what that implies
  about which labels are safe to put in a selector vs. only in
  `metadata.labels`.
- `checksum/config`-style annotations as a rollout-forcing mechanism —
  why an annotation change alone (nothing else about the Deployment
  different) is enough to trigger a rolling update.
- `range` over a Helm map value vs. a list value — the two-variable form
  (`range $k, $v := ...`) vs. the one-variable form.
- `helm template --set` / `-f` layering order, and why `helm lint` and
  `helm template` are both useful before ever touching a real cluster.
