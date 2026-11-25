# Hint 3

Shape of the finished chart, in prose — the YAML is yours to write.

- `templates/_helpers.tpl`: a `spider-platform.fullname` template (e.g.
  release name + chart name) and a `spider-platform.selectorLabels` template
  emitting a fixed 2-key label set (`app.kubernetes.io/name` +
  `app.kubernetes.io/component: spider`). Everything below `include`s these
  so names and labels never drift.

- `templates/deployment.yaml`: `apiVersion: apps/v1`, `kind: Deployment`,
  name from the fullname helper. `spec.replicas` from
  `.Values.spider.replicaCount`; `spec.selector.matchLabels` and
  `spec.template.metadata.labels` both the selector-labels helper; one
  container with the image, `imagePullPolicy`, a `containerPort` on the
  metrics port, env for the target base URL, a `resources` block from
  `.Values.resources` (requests **and** limits, cpu **and** memory), and a
  `livenessProbe` + `readinessProbe` (`httpGet` on the metrics port, `path`
  from `.Values.probes.liveness` / `.readiness`).

- `templates/hpa.yaml`: `apiVersion: autoscaling/v2`,
  `kind: HorizontalPodAutoscaler`. `spec.scaleTargetRef` -> `apiVersion:
  apps/v1`, `kind: Deployment`, `name:` the fullname helper (must equal the
  Deployment's rendered name). `minReplicas`/`maxReplicas` from
  `.Values.autoscaling`; `metrics` a one-entry list, `type: Resource`
  targeting `cpu` Utilization at the configured percentage. Leave a comment
  that queue-depth via a custom-metrics adapter/KEDA is the real answer for a
  spider pool — CPU is the core-k8s stand-in this chart uses on purpose.
  (Optional: wrap the whole file in
  `{{- if .Values.autoscaling.enabled }}` so it can be turned off.)

- `templates/pdb.yaml`: `apiVersion: policy/v1`, `kind: PodDisruptionBudget`,
  `spec.minAvailable` from `.Values.pdb.minAvailable`, `spec.selector.
  matchLabels` the selector-labels helper.

Render with `helm template k8s-bonus/chart` and eyeball that the Deployment's
name, the HPA's `scaleTargetRef.name`, and the label set under both the
Deployment's pod template and the PDB's selector are all identical. If the
validator says "this HPA scales nothing" or "this PDB protects nothing",
that identity broke somewhere.

Live stretch (optional): once installed on kind/k3d, `kubectl scale
deployment spider-platform --replicas=N` and watch workers join/leave the
pool with `kubectl get pods -w`; if metrics-server is installed, generate CPU
load and watch the HPA move the replica count on its own.
