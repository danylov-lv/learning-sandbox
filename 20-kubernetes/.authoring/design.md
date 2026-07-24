# Module 20 design -- SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
infrastructure contract every task and validator in this module depends on:
cluster topology, the fixture app's knobs, the fixed task list with its
verification approach, and the shared-resource rules that keep 22 tasks
from tripping over each other on one long-lived cluster.

This file is the contract for every agent authoring a task directory in
this module. If you change a knob, a port, or a namespace rule here, update
every consumer (scripts, harness, task READMEs/validators) in the same
change.

## Cluster topology

- kind cluster, name `sandbox20`, context `kind-sandbox20`. 1 control-plane
  + 2 workers (`cluster/kind-config.yaml`).
- `disableDefaultCNI: true` + Calico installed by `scripts/cluster-up.sh`.
  This is required, not cosmetic: kind's default CNI (kindnet) does not
  enforce `NetworkPolicy` at all -- a learner could write a completely
  wrong policy in task 14 and see traffic blocked/allowed by coincidence
  rather than by their policy. Calico actually enforces what's written.
- Calico version pinned to **v3.29.1**
  (`https://raw.githubusercontent.com/projectcalico/calico/v3.29.1/manifests/calico.yaml`),
  verified working against kind v0.32.0 / Kubernetes v1.33 during live
  verification of this infrastructure. If a future kind/k8s upgrade breaks
  this pin, bump it here and in `scripts/cluster-up.sh` together.
- API server reachable at `127.0.0.1:6320` (mapped via `apiServerPort`).
- Ingress host ports: control-plane node has `ingress-ready=true` label and
  maps container port 80 -> host `8320`, container port 443 -> host `9320`.
  Task 13 installs ingress-nginx targeting these node ports; nothing else
  in the module should bind them.
- `podSubnet: 10.244.0.0/16` -- Calico's default, chosen to avoid fighting
  the manifest's own IPAM defaults.
- The cluster is meant to live for the whole module: create it once with
  `scripts/cluster-up.sh`, build images once with `scripts/build-images.sh`,
  and leave both running across every task's evenings. `scripts/cluster-down.sh`
  only when the learner wants to reclaim resources or start over clean.

## Fixture app (`app/app.py`)

Single file, stdlib `ThreadingHTTPServer` + `threading` only (no async, no
frameworks). `redis`/`pika` used only in `WORK_MODE=consumer|producer`.
Every behavior is env-knob-driven with a safe default so task authors can
express "broken" states as plain env vars / Deployment fields instead of
forking the app.

### Images

| Tag | Dockerfile | Notes |
|---|---|---|
| `sandbox20-app:1.0` | `Dockerfile` | `APP_VERSION=1.0` baked in via build-arg |
| `sandbox20-app:2.0` | `Dockerfile` | same code, `APP_VERSION=2.0` -- rollout/rollback fixture |
| `sandbox20-app:distroless` | `Dockerfile.distroless` | `gcr.io/distroless/python3-debian12`, no shell -- ephemeral-containers fixture (task 10) |

The distroless build stage uses `python:3.11-slim` (not 3.12) specifically
because `gcr.io/distroless/python3-debian12`'s interpreter is `python3.11`
(verified: `ENTRYPOINT ["/usr/bin/python3.11"]`, `python 3.11.2`) --
dependencies are installed with `pip install --target=/deps` against a
matching interpreter and copied in via `PYTHONPATH=/deps`. `redis`/`pika`
are pure Python (no compiled extensions), so this mostly matters for
hygiene, not correctness.

All three images must be built and `kind load docker-image`d by
`scripts/build-images.sh` before any task's pods can schedule -- there is
no registry, kind's containerd only has what was explicitly loaded.

`scripts/build-images.sh` also builds+loads `redis:t11-repack` -- a
single-platform repack of `redis:7-alpine` (task 11's queue needs a redis
in-cluster; plain `redis:7-alpine`'s multi-platform manifest-list +
provenance attestation cannot be `kind load`ed into containerd on this
setup, so it is rebuilt via `docker build --provenance=false --sbom=false`
`FROM redis:7-alpine`). Any later task needing a stock redis should reuse
this tag rather than reload the multi-platform one.

### Env knobs

| Var | Default | Effect |
|---|---|---|
| `PORT` | `8080` | HTTP listen port |
| `APP_VERSION` | `dev` (baked per image tag) | reported in `/` and used by rollout tasks |
| `START_DELAY_S` | `0` | sleep before binding the socket -- slow-start fixture |
| `READY_DELAY_S` | `0` | `/readyz` returns 503 until this many seconds after start |
| `FAIL_READY` | `0` | `1` = `/readyz` always 503 |
| `FAIL_HEALTH_AFTER_S` | `0` (disabled) | `/healthz` returns 500 after N seconds |
| `CRASH_ON_START` | `0` | `1` = log one grep-able fatal line, exit before binding |
| `CRASH_AFTER_S` | `0` (disabled) | exit after N seconds uptime |
| `EXIT_CODE` | `1` | exit code used by `CRASH_ON_START` / `CRASH_AFTER_S` |
| `MEM_MB` | `0` | allocate and hold N MiB at start |
| `LEAK_MB_PER_S` | `0` (disabled) | grow resident memory by N MiB every second forever -- OOMKill fixture |
| `CPU_BURN_THREADS` | `0` | spawn N tight-loop busy threads |
| `REQUIRED_ENV` | `""` | comma-separated env var names; if any is missing, log + exit 1 (ConfigMap/Secret fixture) |
| `TERM_IGNORE` | `0` | `1` = ignore SIGTERM entirely (bad-citizen fixture; process only dies on SIGKILL) |
| `TERM_GRACE_S` | `25` | internal cap on how long graceful shutdown waits for inflight requests to drain |
| `WORK_MODE` | `server` | `server` \| `consumer` \| `producer` |
| `QUEUE_BACKEND` | `redis` | `redis` \| `rabbitmq` (consumer/producer only) |
| `REDIS_HOST`/`REDIS_PORT`/`QUEUE_KEY` | `localhost`/`6379`/`sandbox20:queue` | redis backend connection |
| `RABBIT_HOST`/`RABBIT_PORT`/`RABBIT_USER`/`RABBIT_PASS`/`QUEUE` | `localhost`/`5672`/`guest`/`guest`/`sandbox20-queue` | rabbitmq backend connection |
| `PROCESS_MS` | `100` | consumer: simulated processing time per item |
| `RATE_PER_S` | `1` | producer: items pushed per second |

### HTTP endpoints

- `GET /` -> `{"app_version", "hostname", "request_count"}`.
- `GET /healthz` -- liveness; see `FAIL_HEALTH_AFTER_S`.
- `GET /readyz` -- readiness; 503 while shutting down, while `FAIL_READY=1`,
  or before `READY_DELAY_S` has elapsed.
- `GET /work?ms=N` -- sleeps N ms then 200. Used to hold connections open
  for graceful-shutdown / zero-downtime tests (in-flight request survives a
  rollout iff the app drains properly and the Service stops routing to it
  in time).
- `GET /env?name=X` -- echoes one env var, but only if `X` starts with
  `APP_` or `CONFIG_` (403 otherwise) -- config/secret tasks assert against
  this rather than exec-ing into the pod.
- `GET /metrics` -- Prometheus text: `app_requests_total` (counter),
  `app_inflight` (gauge), plus `app_queue_depth` (gauge, consumer/producer
  modes) and `app_processed_total` (counter, consumer mode).

### SIGTERM semantics

Default: on SIGTERM the app immediately flips `/readyz` to 503, stops
accepting new HTTP connections, waits (up to `TERM_GRACE_S`) for in-flight
requests to finish, then exits 0. This is what a well-behaved pod looks
like for the zero-downtime task (02). `TERM_IGNORE=1` produces the opposite
fixture: the process never reacts to SIGTERM and only dies when the kubelet
escalates to SIGKILL after `terminationGracePeriodSeconds` -- visible as a
slow, ungraceful pod termination.

## Task list (fixed by the orchestrator)

Namespacing rule: task `NN` uses Kubernetes namespace `t{NN}` (e.g. task 08
uses `t08`) and must never read or write another task's namespace. Every
task's validator creates its namespace via `harness.common.ensure_ns` and
should leave cleanup to the learner/validator, not to other tasks.

Node-mutation rule: a task may taint/label nodes only with keys prefixed
`s20-t{NN}/` (e.g. `s20-t09/dedicated`) and must remove every such
taint/label it added, whether the task passes or fails. Only task 20
(`pdb-vs-node-drains`) may cordon or drain a node, and only after
uncordoning and restoring schedulability on every node it touched.

Cluster-global installs (each owned by one task, installed via a committed,
re-runnable script with a matching teardown script; every later task
depends on these already being installed and must not reinstall or
uninstall them):

| Component | Owning task | Install script |
|---|---|---|
| ingress-nginx | 13-ingress | `13-ingress/scripts/install.sh` (+ `uninstall.sh`) |
| Argo CD + in-cluster Gitea | arc 5 (16-18) | `16-argocd-app-by-hand/scripts/install.sh` (+ `uninstall.sh`) |
| CloudNativePG operator | 15-statefulsets-and-cnpg | `15-statefulsets-and-cnpg/scripts/install.sh` (+ `uninstall.sh`) |
| RabbitMQ, Prometheus, prometheus-adapter | 19-hpa-on-queue-depth | `19-hpa-on-queue-depth/scripts/install.sh` (+ `uninstall.sh`) |

Task list and one-paragraph verification approach for each:

**Arc 1 -- Manifests from zero**
- `01-deployment-service-config` -- Deployment/Service/ConfigMap/Secret
  written by hand. Validator applies the learner's manifests into `t01`,
  waits for rollout, port-forwards the Service, and asserts `/` returns the
  expected `app_version` and `/env?name=CONFIG_*` echoes a value sourced
  from the ConfigMap/Secret (not hardcoded).
- `02-probes-and-zero-downtime` -- fix wrong liveness/readiness probes that
  cause a rolling-update outage. Validator drives sustained `/work?ms=N`
  load through the Service during a rollout (old image -> new image) and
  asserts zero non-2xx responses, using the app's own graceful-shutdown and
  readiness semantics as ground truth.
- `03-jobs-cronjobs-and-resources` -- a scrape-flavored Job/CronJob with
  resource requests/limits. Validator asserts the Job reaches `Complete`,
  the CronJob's schedule/concurrency policy fields are set correctly, and
  every container has both requests and limits set.

**Arc 2 -- Your own Helm chart**
- `04-first-chart-from-manifests` -- promote Arc 1 manifests into a
  from-scratch chart. Validator runs `helm template`/`helm lint` offline,
  then (if a cluster is reachable) `helm install`s into `t04` and checks
  the same behavioral assertions as task 01 against the release.
- `05-chart-advanced-deps-hooks-diffing` -- subchart dependency, a
  pre-install/pre-upgrade hook, and a `helm template` diff workflow.
  Validator renders before/after value sets and asserts the hook resource
  and dependency subchart both appear with the right ordering annotations.
- `06-reverse-engineer-company-template` -- written explanation task (no
  cluster assertions); graded with `harness.check_sections`/`check_answers`
  against a provided umbrella chart the learner must annotate and critique.
- `07-arc2-capstone-package-spider-platform` -- package an earlier
  module's app (06 or 13) as a full chart. Validator is the most thorough
  in the module: lint + template + live install into `t07` + behavioral
  probes against the running release.

**Arc 3 -- Operations and debugging**
- `08-rightsizing-and-oomkill` -- measure a provided workload, set
  requests/limits, and reason about a scripted OOMKill (`LEAK_MB_PER_S`).
  Validator applies a manifest with the learner's resource values, drives
  load, and asserts the container is OOMKilled at the leak's expected time
  window if limits are too low, or survives if right-sized -- both a valid
  answer depending on which the learner argues for in `NOTES.md`.
- `09-pending-pod-zoo` -- a set of scripted Pending pods (resource
  starvation, anti-affinity conflict, taint/toleration mismatch, unbound
  PVC). Validator applies each fixture into `t09`, then checks the
  learner's written diagnosis file names the correct root cause per pod
  from `kubectl describe`/events output it captures itself.
- `10-crashloop-and-distroless` -- triage a CrashLoopBackOff
  (`CRASH_ON_START`/`CRASH_AFTER_S`/`REQUIRED_ENV` fixtures) and debug the
  shell-less `sandbox20-app:distroless` image via ephemeral containers.
  Validator asserts the learner fixed the crash (pod reaches Ready) and
  that an ephemeral debug container was actually used (checks
  `pod.spec.ephemeralContainers` in the pod's history/events) rather than
  swapping the image for a shell-having one.
- `11-arc3-capstone-incident` -- multi-component scripted incident with one
  hidden root cause. Validator seeds the broken state into `t11`, then
  checks the cluster returns to a healthy target state (all Deployments
  available, no CrashLoopBackOff, `/readyz` green through the Service)
  without caring which exact fix path the learner took.

**Arc 4 -- Networking and state**
- `12-services-and-dns-debugging` -- fix a broken Service/DNS chain
  (selector mismatch, wrong port, headless vs ClusterIP misuse). Validator
  runs a probe Job inside `t12` that resolves and curls the target Service
  and asserts success.
- `13-ingress` -- install ingress-nginx (owning script) and write an
  Ingress resource. Validator curls `http://127.0.0.1:8320` with the
  configured `Host` header and asserts it reaches the app.
- `14-networkpolicy-isolation` -- isolate a worker so it can reach only the
  queue and its allowed targets. Validator runs positive and negative probe
  Jobs from inside and outside `t14` and asserts allowed traffic passes and
  denied traffic is actually blocked (this is why Calico, not kindnet, is
  required).
- `15-statefulsets-and-cnpg` -- install the CNPG operator (owning script),
  bring up a Postgres cluster via CR, and observe a simulated failover.
  Validator asserts the CNPG cluster reports the expected number of
  instances healthy and that a forced primary-pod deletion results in a new
  primary within a bounded wait.

**Arc 5 -- Argo CD demystified**
- `16-argocd-app-by-hand` -- install Argo CD + in-cluster Gitea (owning
  script), push the Arc 2 chart to the in-cluster repo, write an
  `Application` CR by hand. Validator queries the Argo CD API/CLI and
  asserts the Application is `Synced`/`Healthy` and points at the learner's
  repo/chart.
- `17-drift-selfheal-waves` -- sync policies, drift self-heal, sync waves
  and hooks. Validator mutates a live resource out-of-band, asserts Argo CD
  reverts it within a bounded wait (self-heal enabled), and checks
  wave/hook ordering annotations on a multi-resource app.
- `18-app-of-apps-and-rollback` -- app-of-apps pattern + `git revert`
  rollback. Validator asserts a parent Application manages the expected
  child Applications and that after a scripted bad commit + learner revert,
  the target app's live state matches the pre-bad-commit chart version.
  Written component: map every field of the work Application template,
  graded with `check_sections`/`check_answers`.

**Arc 6 -- Advanced (optional)**
- `19-hpa-on-queue-depth` -- install RabbitMQ + Prometheus +
  prometheus-adapter (owning script), scale the fixture app's consumer
  deployment via HPA on a custom queue-depth metric. Validator drives the
  producer to push queue depth up, asserts replica count increases, then
  drains the queue and asserts it scales back down, all within bounded
  waits.
- `20-pdb-vs-node-drains` -- PDB behavior under `kubectl drain`. This is
  the only task allowed to cordon/drain nodes. Validator asserts a drain
  respecting the learner's PDB succeeds without violating `minAvailable`,
  then asserts every node is uncordoned and schedulable again at the end
  (whether the task passed or failed).
- `21-helm-vs-kustomize-writeup` -- pure written comparison, no cluster
  assertions; graded with `check_sections`/`check_keywords`/`check_answers`.
- `22-operator-kopf-scrapejob` -- multi-evening capstone: a `ScrapeJob` CRD
  + `kopf`-based operator that spawns worker Deployments and cleans them up
  on CR deletion. Validator applies/deletes CRs against `t22` and asserts
  the expected child Deployments appear/disappear and that operator logs
  show the expected reconcile events.

## Stub convention

- Learner-facing YAML stubs (Deployment/Service/chart templates/etc.) are
  files that exist but contain only a `# TODO(you): ...` skeleton comment
  block -- enough structure to know what's expected, nothing that renders
  into a working resource. They fail validation cleanly (missing
  kind/fields) rather than with a YAML parse error.
- Python stubs (operator handlers, estimate-style helpers where a task
  needs one) raise `NotImplementedError` from every function body the
  learner must fill in.
- Written tasks (`06`, `18`'s mapping component, `21`) ship a `NOTES.md` or
  `ANSWERS.md` template with unfilled `[fill in]` markers per section/
  question, matching the `PLACEHOLDER_MARKERS` the doc-gate helpers reject.

## Repo-wide rules (restated for this module)

- No reference solutions anywhere in this module -- not in hints, not in
  `.authoring/`, not in tests.
- Every validator prints exactly one line on failure
  (`NOT PASSED: <reason>`) and exits 1; exactly `PASSED` (optionally with a
  trailing detail) on success. No raw tracebacks reach the learner --
  wrap entry points in `harness.common.guarded`.
- No absolute wall-clock performance gates. Timing assertions (rollout
  completes, HPA scales, drain finishes) use generous, documented timeouts
  and bounded polling (`wait_until`/`wait_rollout`), never a hardcoded
  "must finish in N seconds" tuned to one machine.
