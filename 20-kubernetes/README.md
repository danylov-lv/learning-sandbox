# 20 - Kubernetes

The real Kubernetes track: from raw manifests written by hand, through designing your own Helm charts, to operations, debugging, networking, state, Argo CD internals, and an optional taste of writing an operator. This stub carries the condensed full spec — future generation sessions build the module from this file.

Status: not generated yet (see GENERATION_STATE.md)

## Calibration

The learner deploys to Kubernetes daily at work — but only via existing charts and an Argo CD template someone else designed. He fills templates; he does not design manifests or charts. Theory is familiar from a course, hands-on experience is thin. Therefore: fundamentals are NOT skipped, but paced fast — practice-first, minimal theory recaps — building toward deep operational skills. Local cluster via kind or k3d. The module is a wide, easy-to-hard progression structured as a ladder of arcs: each arc is several single-evening tasks; later arcs' capstones span multiple evenings.

Verification style throughout: scripted broken/target cluster states plus validator scripts that assert the fixed/deployed state. Hints 1-3 per task, no reference solutions anywhere (global repo rules apply).

## Arc ladder

### Arc 1 — Manifests from zero (foundation, fast pace)

Raw YAML by hand, no Helm. Deployment for a provided worker app, Service, ConfigMap/Secret, liveness/readiness/startup probes — including a task where wrong probes cause a rolling-update outage: observe it, then fix it. Resource requests/limits. Job + CronJob (scraper-flavored scheduled scrape job). Validators assert deployed state and behavior, e.g. a rolling update with zero dropped requests under test load.

### Arc 2 — Your own Helm chart (the centerpiece)

Grow the Arc 1 manifests into a chart from scratch: templates, values.yaml design (what is a value vs what is hardcoded — a design task with a review checklist), helpers/_tpl, conditionals and ranges, chart dependencies, hooks, and `helm template` diffing as a debug workflow. Plus: a realistic company-style worker+api+queue umbrella template is provided — reverse-engineer it, explain every decision, find two questionable ones. Capstone: package one of the sandbox's earlier projects (module 06 or 13) as a proper chart with configurable workers, probes, and resources.

### Arc 3 — Operations and debugging

Requests/limits derived from actual measurements: profile a provided workload and right-size it. OOMKill anatomy. QoS classes and eviction. A Pending-pod zoo — resources, affinity, taints, PVC binding — diagnose each case from events alone. CrashLoopBackOff triage methodology. Ephemeral containers for distroless images. Capstone: a "production incident" — a multi-component app is degraded with a scripted hidden root cause; find it from symptoms.

### Arc 4 — Networking and state

Services and kube-proxy from the inside; ingress; DNS failure debug tasks. NetworkPolicy: isolate scraper-style workers so they can reach only the queue and their targets, verified with tests. StatefulSets vs Deployments and why databases on Kubernetes hurt. Postgres via the CloudNativePG operator locally: simulate failover and observe what the operator does.

### Arc 5 — Argo CD demystified

Install Argo CD locally and deploy the Arc 2 chart through it: an Application spec written by hand, sync policies, drift detection (mutate the cluster, watch self-heal), sync waves and hooks, the app-of-apps pattern (recognize it — it is likely what the work template implements), rollback via git revert. Written task: map every field of the work Application template to what it actually does.

### Arc 6 — Advanced (optional)

HPA on custom metrics (queue depth from RabbitMQ/redpanda). PDB behavior vs scripted node drains. A reasoned Helm vs Kustomize comparison. Optional multi-evening capstone: a minimal operator/CRD on kopf — a ScrapeJob CRD that spawns worker deployments and cleans up after itself. The goal is to demystify operators, no more.
