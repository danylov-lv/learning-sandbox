# Hint 3

Shape of the finished chart, in prose — the YAML is yours to write:

- `templates/deployment.yaml`: `replicas` from
  `.Values.consumer.replicas`; pod labels a small fixed set (e.g. app
  name + component `consumer`) applied consistently and reused by the
  HPA/PDB below; one container running your consumer image, env vars for
  `bootstrap.servers`, `group.id`, and the Postgres DSN (password from a
  Secret, same pattern as module 06's chart) sourced from values; the
  measured `resources` block (requests **and** limits, cpu **and**
  memory).
- `templates/hpa.yaml`: `apiVersion: autoscaling/v2`,
  `kind: HorizontalPodAutoscaler`, `spec.scaleTargetRef` pointing at the
  Deployment by `apiVersion: apps/v1`, `kind: Deployment`, and its exact
  `name`; `minReplicas`/`maxReplicas` from values; `metrics` a one-entry
  list, `type: Resource` targeting `cpu` utilization. Leave the comment
  from values.yaml about KEDA/lag-based scaling being the real answer for
  a Kafka consumer — CPU is a stand-in this chart uses because it stays
  inside core k8s objects.
- `templates/pdb.yaml`: `policy/v1` PodDisruptionBudget,
  `spec.selector.matchLabels` exactly the Deployment's pod labels,
  `minAvailable` (or `maxUnavailable`) from values.
- `templates/secret.yaml`: the Postgres password, `b64enc`'d from a
  value (sandbox-grade; note in NOTES.md what production would do
  instead).

Watching the rebalance once it's deployed: scale the Deployment
(`kubectl scale deployment price-consumer --replicas=N`) and watch
partition ownership move — either in Redpanda Console's consumer-groups
view (http://localhost:8307 if you exposed it, or port-forward) or with
`rpk group describe t03-group` from inside the redpanda container/pod.
Scaling from 1 to 2+ replicas triggers exactly the assign/revoke sequence
task 03's `on_assign`/`on_revoke` callbacks logged to
`ops.t03_rebalance_log` — if your image runs that consumer, cross-check
the k8s-observed rebalance against rows landing in that table.
