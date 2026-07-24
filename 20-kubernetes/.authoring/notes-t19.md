# Authoring notes -- 19-hpa-on-queue-depth

Owning task for **RabbitMQ + Prometheus + prometheus-adapter** (cluster-global
install, `scripts/install.sh` + `uninstall.sh`), all in namespace
`t19-infra` (kept separate from `t19`, which the validator deletes and
recreates on every run). No later task in this module depends on this
stack, but it is still an owning install per `.authoring/design.md` and is
left installed.

## Versions pinned (verified live against this cluster, k8s v1.32.2)

- RabbitMQ **3.13-management** (`rabbitmq:3.13-management`), with
  `rabbitmq_prometheus` enabled via a mounted `enabled_plugins` file
  (must also list `rabbitmq_management` explicitly -- mounting this file
  replaces the image's default enabled-plugins list, it doesn't append to
  it). Per-object (per-queue) metrics are NOT on by default in 3.13's
  `rabbitmq_prometheus` -- only cluster/node aggregates are exposed until
  `application:set_env(rabbitmq_prometheus, return_per_object_metrics,
  true)` is run via `rabbitmqctl eval` after the pod is up. Without this,
  `rabbitmq_queue_messages_ready` never appears with a `queue` label at
  all.
- Auth: custom user `sandbox`/`sandboxpass` via `RABBITMQ_DEFAULT_USER`/
  `RABBITMQ_DEFAULT_PASS`. The default `guest` user is loopback-only by
  RabbitMQ's own policy and refuses connections from other pods -- this
  bit hard the first time (producer/consumer pods got connection
  refused/access-refused errors using `guest`/`guest`).
- Prometheus **v2.55.1** (`prom/prometheus:v2.55.1`), single Deployment,
  no Operator, `scrape_interval: 5s`, scraping
  `rabbitmq.t19-infra.svc.cluster.local:15692` (the `rabbitmq_prometheus`
  plugin's port). `--storage.tsdb.retention.time=6h`, no persistent
  volume -- this stack only exists to feed the adapter.
- prometheus-adapter **v0.12.0**
  (`registry.k8s.io/prometheus-adapter/prometheus-adapter:v0.12.0`).
  Registers `APIService v1beta1.external.metrics.k8s.io`,
  `insecureSkipTLSVerify: true` (self-signed cert, fine for this
  cluster). RBAC: ClusterRole granting `custom.metrics.k8s.io` +
  `external.metrics.k8s.io` `*`/`*`, `system:auth-delegator` binding,
  `extension-apiserver-authentication-reader` RoleBinding in
  `kube-system`, and a `system:metrics-reader` ClusterRole bound to the
  `horizontal-pod-autoscaler` ServiceAccount in `kube-system` (the HPA
  controller's own identity) so it's actually allowed to call the API it
  just registered.

## The exact adapter rule + metric name (the finicky part)

```yaml
externalRules:
  - seriesQuery: 'rabbitmq_queue_messages_ready{queue!=""}'
    resources:
      overrides:
        namespace: {resource: "namespace"}
    name:
      matches: "rabbitmq_queue_messages_ready"
      as: "rabbitmq_queue_messages_ready"
    metricsQuery: 'sum(<<.Series>>{<<.LabelMatchers>>}) by (queue)'
```

Two non-obvious things this rule depends on, both discovered by trial and
error against live errors, not from docs:

1. **RabbitMQ's own series carry no `namespace` label** (RabbitMQ has no
   concept of Kubernetes namespaces). Without one, prometheus-adapter's
   External metric handler errors with `unable to convert resource
   namespaces into label: no generic resource label form specified for
   this metric` the instant an HPA (which always queries External
   metrics scoped to a namespace, e.g.
   `.../namespaces/t19/rabbitmq_queue_messages_ready`) asks for it. Fix:
   Prometheus's own scrape config injects a static `namespace: t19` label
   on the rabbitmq target (Prometheus `static_configs.labels`, standing
   in for "the namespace of the workload that owns this queue"), and the
   adapter rule's `resources.overrides.namespace: {resource: "namespace"}`
   tells it that label plays the role of the k8s "namespace" resource.
   Without `resources.overrides` at all, an External rule that specifies
   `resources: {}` still tries (and fails the same way) to inject a
   namespace matcher -- there's no way to make it skip namespace scoping
   entirely once a request comes in on a namespaced path.
2. `metricsQuery` uses `sum(...) by (queue)`, not a bare `sum(...)` --
   needed so the discovery/relist step can enumerate one series per
   queue (only one queue exists in this task, but the `by (queue)` is
   what lets the adapter report `metricLabels: {"queue": "..."}` on the
   value response, which is what the HPA's `external.metric.selector`
   actually has to match against).

**Verified query (exactly what an HPA issues):**

```
kubectl --context kind-sandbox20 get --raw \
  '/apis/external.metrics.k8s.io/v1beta1/namespaces/t19/rabbitmq_queue_messages_ready?labelSelector=queue%3Dsandbox20-queue'
```

Live response with a real backlog:
`{"kind":"ExternalMetricValueList",...,"items":[{"metricName":"rabbitmq_queue_messages_ready","metricLabels":{"queue":"sandbox20-queue"},"value":"25"}]}`
-- confirmed moving from `0` (empty queue) up to the real backlog count
and back to `0` after a purge, live, before writing the validator.

## Git Bash / MSYS gotcha (non-obvious, cost real debugging time)

`kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1"` run directly
from a bash script on this Windows/Git-Bash environment gets its
`/apis/...` argument silently rewritten into a Windows path (observed:
`C:/Program Files/Git/apis/external.metrics.k8s.io/v1beta1`) before
`kubectl.exe` ever sees it, producing a confusing 404 that looks like a
real adapter problem but isn't. `scripts/install.sh` now exports
`MSYS_NO_PATHCONV=1` at the top to disable this rewrite for every command
in the script. This does NOT affect `tests/validate.py` -- Python's
`subprocess.run(["kubectl", ...])` goes straight to `CreateProcess`
without MSYS's argv rewriting, confirmed by testing the identical `get
--raw` call from `uv run python` directly (worked first try, no env var
needed).

## Task / grading

Learner writes `src/hpa.yaml` (an `autoscaling/v2` HPA targeting
`Deployment/queue-consumer` with an `External` metric on
`rabbitmq_queue_messages_ready`, `selector.matchLabels: {queue:
sandbox20-queue}`). Given `producer.yaml`/`consumer.yaml` establish a
baseline-balanced ~2 items/s producer vs. one ~2 items/s consumer
replica. Validator: confirms the stack + metric are live, applies
producer/consumer + the learner's HPA into fresh `t19`, purges the queue,
raises the producer's `RATE_PER_S` to 40 to force a backlog, asserts
`queue-consumer` replicas increase (bounded wait), then scales the
producer to 0 and asserts the queue drains to 0 and replicas decrease
again (bounded, generous -- accommodates the HPA's 300s default
`scaleDown.stabilizationWindowSeconds` even though the reference test
used 60s for a faster iteration loop). A gated `NOTES.md` reflection
covers the metrics pipeline, why queue depth beats CPU here, the
learner's own observed replica counts, and the `ceil(currentValue /
averageValue)` arithmetic for their chosen threshold.

## Verified

Stock (unfilled `src/hpa.yaml` stub) fails cleanly:
`NOT PASSED: kubectl apply -f hpa.yaml failed: error: no objects passed to apply`,
exit 1, one line, namespace `t19` cleaned up.

Reference pass-path proven live TWICE by the authoring subagent, both
directions of the scale cycle actually observed (not just asserted):

- First pass: manual walk-through with a throwaway reference HPA
  (`minReplicas: 1, maxReplicas: 5, averageValue: "10",
  scaleDown.stabilizationWindowSeconds: 60`) -- replicas observed going
  1 -> 3 -> 5 within ~90s of raising producer rate, then, after stopping
  the producer and the queue draining (~2900 backlog took ~5 minutes to
  drain at ~10 items/s aggregate consumer capacity across 5 replicas --
  this large backlog was a side effect of leaving the high rate running
  during investigation, not a claim about typical backlog size), replicas
  observed going 5 -> 3 -> 1 within ~90s of the queue hitting 0. Full
  cycle: PASSED with `queue-consumer replicas went 1 -> 3 (queue backed
  up) -> 1 (queue drained) within bounded waits`.
- Second pass: full `tests/validate.py` run (the actual validator code,
  including the `NOTES.md` doc-gate) with the same throwaway reference
  HPA and a temporarily-filled `NOTES.md`, both reverted byte-identical
  afterward (sha256 confirmed for both `src/hpa.yaml` and `NOTES.md`
  before/after). Also PASSED end to end, this run's cycle: 1 -> 3 -> 1,
  scale-up within ~50s, full drain-then-scale-down within ~2m45s.

No reference solution committed anywhere -- both `src/hpa.yaml` and
`NOTES.md` are back to their original TODO/`[fill in]` state (sha256
verified identical to pre-test).

Scale-down was NOT deferred -- both live runs observed the full
scale-up-then-down cycle end to end within the session, using a shorter
`stabilizationWindowSeconds` (60s) than the 300s default specifically to
keep verification runs practical; the validator's own bound
(`DRAIN_AND_SCALE_DOWN_TIMEOUT_S = 900`) is generous enough to also accept
a learner who leaves the default 300s window.

## Gotchas for whoever touches this next

- If `app/app.py`'s RabbitMQ wiring ever changes, note that
  `RabbitQueue.depth()` in the fixture app polls via `queue_declare(...,
  passive=True)` -- a different mechanism than what this task's metric
  pipeline uses (RabbitMQ's own `rabbitmq_prometheus` plugin scraped by
  Prometheus). The two numbers should agree but are fetched completely
  independently; don't assume a fix to one automatically fixes the other.
- `rabbitmqadmin` (used by `tests/validate.py`'s `_purge_queue` and by
  this authoring session's manual verification) is baked into the
  `rabbitmq:3.13-management` image already -- no separate install step
  needed, `kubectl exec` straight into the `rabbitmq` Deployment's pod.
