# 20 - Kubernetes

The real Kubernetes track: from raw manifests written by hand, through
designing your own Helm charts, to operations, debugging, networking,
state, Argo CD internals, and an optional taste of writing an operator.

## Calibration

At work you deploy to Kubernetes daily -- but only via existing charts and
an Argo CD template someone else designed. You fill in `values.yaml` and
move on; you don't design manifests or charts, and the theory from a course
a while back has faded against thin hands-on practice. This module doesn't
re-teach fundamentals from scratch, but doesn't skip them either: it moves
fast through the basics and spends most of its weight on the operational
skills that never come up when someone else's chart already works --
debugging a Pending pod, tracing why a rollout dropped requests, reading
what Argo CD's sync status is actually telling you.

The module is a ladder of six arcs, each a handful of single-evening tasks,
easy to hard. Verification throughout is scripted: a validator deploys or
mutates cluster state, and your fix (or your diagnosis) is checked
behaviorally against a running cluster -- not by reading your YAML for
style. Every task has three escalating hints and no reference solution
anywhere in this repository.

## Prerequisites

- **Docker Desktop** (or another Docker Engine) running, with enough
  resources allotted for a 3-node kind cluster plus whatever the current
  task installs (Argo CD, CNPG, Prometheus, ...). 4 CPUs / 8 GiB RAM
  dedicated to Docker is a comfortable floor.
- **kind** -- `https://kind.sigs.k8s.io/docs/user/quick-start/#installation`
- **kubectl** -- `https://kubernetes.io/docs/tasks/tools/#kubectl`
- **helm** -- `https://helm.sh/docs/intro/install/`
- **uv** -- `https://docs.astral.sh/uv/getting-started/installation/`

Optional, needed only by specific arcs: the `argocd` CLI (arc 5) and the
`docker` CLI (already covers image builds).

## Cluster lifecycle

The cluster is long-lived across the whole module -- create it once, keep
it running, tear it down only when you want to reclaim resources or start
fresh.

```bash
cd 20-kubernetes
bash scripts/cluster-up.sh      # once: creates kind cluster "sandbox20" + installs Calico
bash scripts/build-images.sh    # once: builds & loads the fixture app's 3 images
uv sync                         # once: installs the validator/harness dependencies

# work through tasks across many evenings; the cluster survives reboots
# of individual tasks and of your machine (as long as Docker Desktop is
# running and the kind cluster's containers weren't removed)

bash scripts/cluster-down.sh    # only when you're done or want a clean slate
```

`cluster-up.sh` is idempotent: running it again with the cluster already up
just re-applies Calico and re-checks node health. Calico (not kind's default
CNI) is required because `NetworkPolicy` enforcement is load-bearing for
task 14 -- kind's default CNI would silently let denied traffic through.

`build-images.sh` builds `sandbox20-app:1.0`, `sandbox20-app:2.0` (same
code, different baked `APP_VERSION` -- used by rollout/rollback tasks), and
`sandbox20-app:distroless` (no shell, used by the ephemeral-containers
debugging task), then `kind load`s all three. There is no registry: kind's
containerd only has what was explicitly loaded, so re-run this script
whenever `app/app.py` changes.

## The fixture app

Every task in this module deploys the same single-file Python app
(`app/app.py`): an HTTP server (and optional queue consumer/producer) whose
entire behavior -- startup delay, crash timing, memory leaks, probe
failures, graceful vs. ungraceful shutdown, required env vars -- is
controlled by environment variables with safe defaults. Task READMEs tell
you which knobs are relevant; you write the Kubernetes objects that wire
those knobs to a realistic failure or success mode.

## Namespace convention

Task `NN` deploys into Kubernetes namespace `t{NN}` (e.g. task 8 uses
`t08`). Validators create and use only their own task's namespace. If
you're poking around with `kubectl` while working a task, stay inside your
task's namespace so you don't collide with fixtures another task installed
cluster-wide (ingress-nginx, Argo CD, CNPG, ...).

## How validation works

Each task directory follows the repo-wide layout (`README.md`, `src/`,
`tests/`, `hints/hint-{1,2,3}.md`, `NOTES.md`). Run a task's validator from
inside the task directory:

```bash
cd 20-kubernetes/01-deployment-service-config
uv run python tests/validate.py
```

`uv sync` at the module root (done once above) covers every task's
dependencies -- there's no per-task `pyproject.toml`. A validator prints
exactly one line on failure (`NOT PASSED: <reason>`) and `PASSED` on
success; no raw tracebacks. If a validator tells you the cluster isn't up,
that's the module's `require_cluster()` check -- run `bash
scripts/cluster-up.sh` from `20-kubernetes/` and try again.

Hints escalate: `hint-1.md` points in a direction, `hint-2.md` narrows to a
specific mechanism, `hint-3.md` is close to pseudocode. There are no
reference solutions anywhere in this module -- not in hints, not in
`.authoring/`, not in the tests.

## Tasks

22 tasks across 6 arcs (arc 6 optional). Estimated 12-15 evenings total;
the arc capstones (07, 11, 22) each run several evenings.

| # | Task | Arc | Evenings |
|---|---|---|:---:|
| 01 | deployment-service-config | 1 -- Manifests from zero | 1 |
| 02 | probes-and-zero-downtime | 1 -- Manifests from zero | 1 |
| 03 | jobs-cronjobs-and-resources | 1 -- Manifests from zero | 1 |
| 04 | first-chart-from-manifests | 2 -- Your own Helm chart | 1 |
| 05 | chart-advanced-deps-hooks-diffing | 2 -- Your own Helm chart | 1-2 |
| 06 | reverse-engineer-company-template | 2 -- Your own Helm chart | 1 |
| 07 | arc2-capstone-package-spider-platform | 2 -- Your own Helm chart | 2-3 |
| 08 | rightsizing-and-oomkill | 3 -- Operations and debugging | 1 |
| 09 | pending-pod-zoo | 3 -- Operations and debugging | 1-2 |
| 10 | crashloop-and-distroless | 3 -- Operations and debugging | 1 |
| 11 | arc3-capstone-incident | 3 -- Operations and debugging | 2 |
| 12 | services-and-dns-debugging | 4 -- Networking and state | 1 |
| 13 | ingress | 4 -- Networking and state | 1 |
| 14 | networkpolicy-isolation | 4 -- Networking and state | 1 |
| 15 | statefulsets-and-cnpg | 4 -- Networking and state | 1-2 |
| 16 | argocd-app-by-hand | 5 -- Argo CD demystified | 1 |
| 17 | drift-selfheal-waves | 5 -- Argo CD demystified | 1 |
| 18 | app-of-apps-and-rollback | 5 -- Argo CD demystified | 1-2 |
| 19 | hpa-on-queue-depth (optional) | 6 -- Advanced | 1-2 |
| 20 | pdb-vs-node-drains (optional) | 6 -- Advanced | 1 |
| 21 | helm-vs-kustomize-writeup (optional) | 6 -- Advanced | 1 |
| 22 | operator-kopf-scrapejob (optional) | 6 -- Advanced | 2-3 |

### Arc 1 -- Manifests from zero

Raw YAML by hand, no Helm. Deployment for the fixture app, Service,
ConfigMap/Secret, liveness/readiness/startup probes -- including a task
where wrong probes cause a rolling-update outage: observe it, then fix it.
Resource requests/limits. Job + CronJob.

### Arc 2 -- Your own Helm chart

Grow the Arc 1 manifests into a chart from scratch: templates,
`values.yaml` design, helpers/`_helpers.tpl`, conditionals and ranges,
chart dependencies, hooks, and `helm template` diffing as a debug workflow.
Reverse-engineer a realistic company-style umbrella chart and explain every
decision. Capstone: package an earlier module's app as a proper chart.

### Arc 3 -- Operations and debugging

Right-size requests/limits from actual measurements. OOMKill anatomy. A
Pending-pod zoo diagnosed from events alone. CrashLoopBackOff triage and
ephemeral-container debugging of a distroless image. Capstone: a
"production incident" with a scripted hidden root cause.

### Arc 4 -- Networking and state

Services and DNS debugging. Ingress. NetworkPolicy isolation, enforced for
real by Calico. StatefulSets vs Deployments, Postgres via the CloudNativePG
operator, and a simulated failover.

### Arc 5 -- Argo CD demystified

Install Argo CD locally, deploy the Arc 2 chart through a hand-written
`Application`, watch drift self-heal, work through sync waves and hooks,
recognize and build the app-of-apps pattern, roll back via `git revert`.

### Arc 6 -- Advanced (optional)

HPA on a custom metric (RabbitMQ queue depth). PDB behavior under scripted
node drains. A reasoned Helm vs. Kustomize write-up. Optional multi-evening
capstone: a minimal `kopf` operator for a `ScrapeJob` CRD.
