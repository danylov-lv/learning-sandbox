# k8s-bonus — Scaling the Consumer Group for Real

Optional. Zero capstone weight — skip it freely; nothing else in this
module depends on it. It exists because "add another consumer" is a
one-line `docker compose up --scale` in this module's stack, and a
`kubectl scale` one-liner on a shared cluster, but the mechanism behind
that one-liner — a consumer-group rebalance — is exactly what task 03
made you watch happen from inside a single process. This bonus makes you
watch it happen from the outside, by scaling the Deployment k8s manages
for you.

## Backstory

Task 03 put you inside one consumer-group member: you instrumented
`on_assign`/`on_revoke`, ran a second member by hand, and watched the
coordinator take partitions away from the first and hand them to the
second. That was you starting a second process manually and pointing it
at the same group id.

On a real cluster, nobody starts a second process manually — they change
a replica count, or they let a HorizontalPodAutoscaler do it under load,
and k8s adds or removes pods for them. Each pod add/remove is a consumer
joining or leaving the group, and each one triggers the exact rebalance
task 03 made visible. This bonus deploys the module's consumer as a
Kubernetes Deployment with multiple replicas, adds an HPA so replica
count can move on its own, and a PodDisruptionBudget so voluntary
disruptions (node drains, rolling updates) don't take out every member
at once — then has you trigger the same rebalance task 03 did, this time
with `kubectl scale`.

## What's given

- `src/Dockerfile` — a TODO skeleton (python-slim + uv). You write the
  real one, wrapping whichever consumer script you point it at (task
  03's is the natural pick — it already logs the rebalance).
- `src/helm/price-consumer/` — a chart skeleton written from scratch:
  `Chart.yaml`, a `values.yaml` full of TODOs, and an empty `templates/`
  directory. Deliberately no `helm create` boilerplate — every template
  you ship is one you wrote and can defend.
- `tests/validate.py` — offline-first validator (renders and lints the
  chart; needs `helm` on PATH); a live section runs only if a kind
  cluster is reachable and skips itself with a notice otherwise.

## What's required

1. **Containerize a consumer.** Finish `src/Dockerfile`: python-slim
   base, dependencies via uv, one of this module's consumer scripts as
   the entrypoint, SIGTERM handled so a scale-down leaves the group
   cleanly. Build it and load it into your kind cluster.
2. **Write the chart from scratch.** In
   `src/helm/price-consumer/templates/`:
   - a **Deployment** running the consumer with `replicas` from values,
     a consistent pod label set, and a container whose
     `resources.requests` **and** `resources.limits` set both cpu and
     memory,
   - a **HorizontalPodAutoscaler** (`autoscaling/v2`) targeting that
     Deployment, with `minReplicas`/`maxReplicas` and at least one
     metric (CPU utilization is fine here — see the note in
     `values.yaml` about why lag-based scaling via KEDA would be the
     real-world choice, and why this chart sticks to core k8s objects
     instead),
   - a **PodDisruptionBudget** whose `spec.selector.matchLabels` matches
     the Deployment's pod labels and sets `minAvailable` or
     `maxUnavailable`.
3. **Derive resources from measurement.** Run the consumer, measure it
   (`kubectl top pod` with metrics-server, or `docker stats` against the
   container) across a few poll cycles under some produced load, set the
   Deployment's requests/limits from what you saw, and write the
   measured numbers into `values.yaml` as comments next to the values
   they justify. Copy-pasted `100m/128Mi` is specifically checked for
   and called out.
4. **Trigger and observe a rebalance.** Deploy with `replicas: 1`, confirm
   the single pod owns every partition, then
   `kubectl scale deployment price-consumer --replicas=2` (or 3) and
   watch the coordinator reassign partitions — in Redpanda Console's
   consumer-groups view, with `rpk group describe`, or by watching new
   rows land in `ops.t03_rebalance_log` if your image runs task 03's
   consumer. Scale back down and watch it happen again in reverse.
5. **Fill in `NOTES.md`** — the measurement table, the HPA/PDB choices,
   and what you observed during the rebalance.

## Running it

Offline (always run, no cluster needed):

```bash
cd 07-streaming/k8s-bonus
uv run python tests/validate.py
```

Live (optional — needs a kind/minikube cluster and this module's stack):

```bash
# from 07-streaming/, with docker compose up -d already run
docker build -t price-consumer:dev -f k8s-bonus/src/Dockerfile .
kind load docker-image price-consumer:dev
helm install price-consumer k8s-bonus/src/helm/price-consumer \
  --set image.repository=price-consumer --set image.tag=dev
kubectl scale deployment price-consumer --replicas=3
kubectl get pods -w   # watch new pods join
rpk group describe t03-group   # or open Redpanda Console at :8307
```

## Completion criteria

```bash
uv run python tests/validate.py
```

PASSED requires (offline, always run): the chart renders via
`helm template` and passes `helm lint`; the rendered output contains a
Deployment with both requests and limits set (cpu and memory; a
warning — not a failure — if they equal the classic copy-paste
defaults), a HorizontalPodAutoscaler (`autoscaling/v2`) whose
`scaleTargetRef` names that Deployment and which has `minReplicas`,
`maxReplicas`, and at least one metric, and a PodDisruptionBudget whose
selector matches the Deployment's pod labels and sets `minAvailable` or
`maxUnavailable`. The live section (kind cluster reachable) additionally
checks the release is installed; when no cluster is reachable it prints
a notice and skips, it does not fail.

## Estimated evenings

1

## Topics to read up on

- Consumer-group rebalancing (you covered the mechanism in task 03 —
  this is the same thing, triggered by k8s pod churn instead of a
  manually started process)
- HorizontalPodAutoscaler v2: the `metrics` array shape, `Resource` vs
  `Pods`/`External` metric types, and why CPU is a weak proxy for a
  Kafka consumer's real bottleneck (lag)
- KEDA's Kafka scaler (`ScaledObject` on consumer-group lag) as the
  production-grade alternative to a CPU-based HPA for this workload —
  read about it, don't build it; it's a separate operator/CRD outside
  this chart's scope
- PodDisruptionBudgets on a multi-replica Deployment: how `minAvailable`
  interacts with a rolling scale-down or a node drain
- Reaching host services (broker, warehouse) from inside kind:
  `host.docker.internal`, kind `extraPortMappings`
- Loading a locally built image into kind (`kind load docker-image`) vs.
  pushing to a registry
- `rpk group describe` / Redpanda Console's consumer-groups view for
  inspecting live partition ownership
- Requests vs. limits and QoS classes (same ground module 06's bonus
  covered — apply it here to a differently-shaped workload)
