# Hint 3

If `kubectl apply -f src/hpa.yaml` succeeds and `kubectl get hpa
queue-consumer-hpa` shows the object, but `TARGETS` stays `<unknown>/...`
instead of a number, the HPA controller itself is failing to fetch the
metric -- this is a different failure mode than "my threshold is wrong"
and needs different debugging:

```bash
kubectl --context kind-sandbox20 -n t19 describe hpa queue-consumer-hpa
```

Read the `Conditions` block at the bottom, specifically `ScalingActive`.
`False` with a reason like `FailedGetExternalMetric` (and a message
naming the metric) means the HPA controller asked the
`external.metrics.k8s.io` API for exactly the metric name + label
selector you wrote in `src/hpa.yaml`, and got an error back. The most
common causes, roughly in order of likelihood:

- The metric `name` in your HPA doesn't exactly match
  `rabbitmq_queue_messages_ready` (typo, wrong case, or the singular vs.
  plural form of "message").
- `selector.matchLabels` doesn't match `{queue: sandbox20-queue}` exactly
  -- a missing selector, an extra unmatched label, or the wrong queue name
  all produce "no series found," not a partial match.
- `scripts/install.sh` hasn't actually finished (or was interrupted) --
  re-run it; it doesn't exit successfully until it has confirmed this
  exact metric is queryable on its own.

If instead the HPA shows a number under `TARGETS` immediately and it
never changes even while you can see (via the metric query from hint 1)
that the real value *is* changing, check that you're pointed at
`scaleTargetRef.name: queue-consumer` and not some other name -- an HPA
targeting a Deployment that doesn't exist yet, or a typo'd name, fails
silently on the scaling side while still reporting metric values
correctly (the metric query and the scale target are two independent
parts of the spec).
