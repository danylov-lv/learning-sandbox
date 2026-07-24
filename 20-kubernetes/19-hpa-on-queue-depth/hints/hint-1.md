# Hint 1

Before writing any YAML, spend five minutes just querying the metric by
hand and watching it move -- guessing at the shape of an HPA's `external`
metric block without ever having seen a real response from that API is
how most of the "finicky" failures in this task happen.

```bash
kubectl --context kind-sandbox20 get --raw \
  '/apis/external.metrics.k8s.io/v1beta1/namespaces/t19/rabbitmq_queue_messages_ready?labelSelector=queue%3Dsandbox20-queue'
```

Run it once with the queue empty, note the `value`. Then push a few dozen
messages in some other way (or just apply `given/producer.yaml` and let it
run for ten seconds) and run the same command again -- the `value` should
have moved. If it hasn't moved, or the command errors instead of returning
JSON, the problem is upstream of anything you're writing: either
`scripts/install.sh` hasn't been run, or something in the RabbitMQ ->
Prometheus -> adapter chain isn't wired the way `scripts/install.sh` set
it up. Fix that before touching `src/hpa.yaml` at all.

Two structural things this query result tells you directly:

- `"namespaced": true` in the discovery response (or just: the URL you
  had to use has `/namespaces/t19/` in it) -- an External metric is still
  requested *within* a namespace, exactly like a Pods or Object metric,
  even though the thing it measures (a RabbitMQ queue) has no concept of
  Kubernetes namespaces at all. Your `HorizontalPodAutoscaler` needs to
  live in the same namespace as `queue-consumer` (`t19`) for this to line
  up.
- `"metricLabels": {"queue": "sandbox20-queue"}` in the value response --
  this is the label your HPA's `external.metric.selector.matchLabels`
  must match. Get the queue name wrong (or omit the selector entirely, if
  there were more than one queue's series in play) and you'd either match
  nothing or match the wrong series.
