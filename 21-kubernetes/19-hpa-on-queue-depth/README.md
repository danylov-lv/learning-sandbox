# 19 — HPA on queue depth

## Backstory

The scraper platform's worker pool has been CPU-based-autoscaled since day
one, and it has never once made sense: workers spend nearly all their time
blocked on network I/O waiting for downstream sites, so CPU usage barely
moves no matter how backed up the actual work queue gets. Meanwhile the
number that *does* tell you whether workers are keeping up — how many jobs
are sitting in the queue waiting to be picked up — isn't a resource metric
Kubernetes knows about at all. It lives inside RabbitMQ, not inside any
pod's cgroup.

This task wires that number into the same autoscaling machinery CPU-based
HPAs use, via the Kubernetes **external metrics API**: RabbitMQ exposes
per-queue depth as a Prometheus metric, Prometheus scrapes it, and
`prometheus-adapter` republishes it as an external metric an HPA can
target directly. Once that pipeline exists, "scale consumers on queue
depth" is a normal `HorizontalPodAutoscaler`, not a bespoke controller.

## What's given

- `scripts/install.sh` (+ `uninstall.sh`) — installs RabbitMQ, a minimal
  Prometheus, and `prometheus-adapter` cluster-wide, all in namespace
  `t19-infra` (deliberately separate from `t19`, which gets deleted and
  recreated on every validator run — this stack has to survive that). This
  is a cluster-global install owned by this task (see
  `.authoring/design.md`); every later task in this module assumes it's
  already there. Run it **once**, yourself, before anything else in this
  task:

  ```bash
  bash scripts/install.sh
  ```

  It's idempotent — safe to re-run — and it doesn't exit until it has
  confirmed the external metric described below is actually queryable, so
  a clean exit means the whole pipeline is live, not just "pods Running."
  Don't run `scripts/uninstall.sh` unless you specifically want to tear it
  down and re-verify the install yourself.

  RabbitMQ's queue in this task is `sandbox20-queue`, reachable from
  inside the cluster at `rabbitmq.t19-infra.svc.cluster.local:5672`
  with user `sandbox` / password `sandboxpass` (the default `guest` user
  is restricted to loopback connections in RabbitMQ, so it can't be used
  from another pod — this is a real RabbitMQ gotcha, not an arbitrary
  choice).

- `given/producer.yaml` / `given/consumer.yaml` — the fixture app's
  `WORK_MODE=producer` and `WORK_MODE=consumer` Deployments, already
  wired to that queue. The validator applies both into `t19` itself; you
  don't edit them. Baseline: the producer pushes ~2 items/s, one consumer
  replica processes ~2 items/s (`PROCESS_MS=500`) — balanced, so the queue
  sits near empty until the validator deliberately raises the producer's
  rate.

- **The metric contract** — this is the part you need to query yourself
  before writing anything:

  - Metric name: **`rabbitmq_queue_messages_ready`**
  - Exposed as an **External** metric (not a Pods/Object metric — there's
    no Kubernetes object backing a RabbitMQ queue), scoped per-namespace,
    selected by label `queue: sandbox20-queue`.
  - Query it exactly the way an HPA does:

    ```bash
    kubectl --context kind-sandbox20 get --raw \
      '/apis/external.metrics.k8s.io/v1beta1/namespaces/t19/rabbitmq_queue_messages_ready?labelSelector=queue%3Dsandbox20-queue'
    ```

    (On Git Bash / MSYS, that leading `/apis/...` argument can get
    silently rewritten into a Windows path before `kubectl` ever sees it —
    if the command above errors with something that looks like a
    filesystem path instead of a 404/JSON, prefix it with
    `MSYS_NO_PATHCONV=1`.)

  A healthy response looks like:

  ```json
  {"kind":"ExternalMetricValueList","apiVersion":"external.metrics.k8s.io/v1beta1",
   "items":[{"metricName":"rabbitmq_queue_messages_ready","metricLabels":{"queue":"sandbox20-queue"},
             "value":"0"}]}
  ```

- `src/hpa.yaml` — a `# TODO(you): ...` stub. This is the only file you
  write.

## What's required

Write a `HorizontalPodAutoscaler` (`autoscaling/v2`) in `src/hpa.yaml`:

- `metadata.name: queue-consumer-hpa`.
- `spec.scaleTargetRef` pointing at the given `Deployment/queue-consumer`.
- `minReplicas` / `maxReplicas` of your choice (`minReplicas >= 1`,
  `maxReplicas > minReplicas` — leave real headroom to actually observe
  scaling).
- one metric, `type: External`, targeting
  `rabbitmq_queue_messages_ready` with
  `selector.matchLabels: {queue: sandbox20-queue}`, and a `target` you
  choose (an `AverageValue` target is the natural fit here: it reads as
  "how many queued messages should each consumer replica be responsible
  for," and the HPA computes `desiredReplicas = ceil(currentValue /
  averageValue)` directly from that).

Optional but worth doing deliberately: an HPA's default
`behavior.scaleDown.stabilizationWindowSeconds` is **300s** — a real
production choice to avoid flapping, but it means the validator's
scale-down assertion has to wait that long if you leave it at the default.
Setting a shorter `stabilizationWindowSeconds` for this exercise (e.g.
`60`) is a legitimate, real choice too, and makes your own feedback loop
much faster while you're iterating — the validator's bound is generous
enough to accept either.

## Completion criteria

From this task directory (after `scripts/install.sh` has been run once,
either by you or already by a previous session):

```bash
uv run python tests/validate.py
```

The validator (namespace `t19`, recreated fresh, deleted at the end
whether you pass or fail; the monitoring stack in `t19-infra` is left
installed):

1. Confirms RabbitMQ, Prometheus, and `prometheus-adapter` are installed
   and the external metric is live (points at `scripts/install.sh` if
   not).
2. Applies `given/producer.yaml` and `given/consumer.yaml`, purges the
   queue for a clean baseline, then applies your `src/hpa.yaml` and checks
   its structural contract (targets `Deployment/queue-consumer`, has an
   `External` metric named `rabbitmq_queue_messages_ready`).
3. Raises the producer's throughput so the queue backs up, and asserts
   `queue-consumer`'s replica count **increases** within a bounded wait.
4. Stops the producer, waits for the queue to drain to 0, and asserts
   replica count **decreases** again within a bounded (generous — it
   accommodates the 300s default stabilization window) wait.

## Estimated evenings

1-2

## Topics to read up on

- HPA v2 metric types — `Resource` (CPU/memory, what almost every HPA
  tutorial uses), `Pods`, `Object`, and `External` — and specifically why
  a RabbitMQ queue depth has to be `External`: it isn't a property of any
  Pod or Kubernetes object, it lives entirely inside RabbitMQ.
- The `custom.metrics.k8s.io` / `external.metrics.k8s.io` APIs: these
  don't exist until something (here, `prometheus-adapter`) registers an
  `APIService` implementing them — Kubernetes ships no built-in
  implementation, unlike `metrics.k8s.io` (metrics-server).
- `prometheus-adapter`'s rule config (`externalRules`): `seriesQuery` (what
  Prometheus series to consider), `metricsQuery` (the PromQL template
  actually run), and `resources.overrides` (how a Prometheus label gets
  mapped to a Kubernetes API concept like "namespace" — required for
  scoping a metric that has no Kubernetes-native namespace label of its
  own).
- Why queue depth beats CPU for worker autoscaling: I/O-bound workers can
  sit at near-zero CPU while a queue grows unbounded behind them, and
  CPU-based HPAs never notice.
- HPA scale-up vs scale-down `behavior`: independent stabilization windows
  and policies per direction, and why scale-down defaults to a much more
  conservative window than scale-up (avoiding flapping vs. reacting fast to
  real load).
- `AverageValue` vs `Value` targets on an External metric, and what
  `desiredReplicas = ceil(currentValue / averageValue)` means in practice
  for picking a threshold.
