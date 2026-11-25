# Hint 2

Narrowing each piece.

- **Labels via a helper.** In `_helpers.tpl`, define two named templates: one
  for the chart's full name (e.g. `{{- define "spider-platform.fullname" -}}`)
  and one for the selector labels (a small fixed set — `app.kubernetes.io/name`
  and `app.kubernetes.io/component: spider` is plenty). `include` the label
  helper in the Deployment's `spec.selector.matchLabels`, its
  `spec.template.metadata.labels`, and the PDB's `spec.selector.matchLabels`.
  Same bytes in all three, guaranteed.

- **The Deployment container.** `replicas: {{ .Values.spider.replicaCount }}`;
  image from `{{ .Values.image.repository }}:{{ .Values.image.tag }}` with
  `imagePullPolicy`; a `containerPort` for `.Values.spider.metricsPort`; env
  wiring the target base URL; a `resources:` block piped straight from
  `.Values.resources` (`{{- toYaml .Values.resources | nindent 12 }}` saves
  you retyping the tree); and `livenessProbe`/`readinessProbe` as `httpGet`
  on the metrics port + each probe's `path` from `.Values.probes`.

- **The HPA metric.** For `autoscaling/v2` a single Resource metric is the
  whole entry:
  `type: Resource`, `resource.name: cpu`, `resource.target.type: Utilization`,
  `resource.target.averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}`.
  It's easy to over-nest — that's all four lines. `scaleTargetRef` must carry
  `apiVersion: apps/v1`, `kind: Deployment`, and the EXACT rendered Deployment
  name (reuse your fullname helper).

- **The PDB.** `policy/v1`, `spec.minAvailable: {{ .Values.pdb.minAvailable }}`,
  `spec.selector.matchLabels` = your label helper. Pick `minAvailable` OR
  `maxUnavailable`, never both — the API rejects a spec that sets neither and
  the intent is muddy if you set both.

- **Measuring the spider.** metrics-server + `kubectl top pod`, or
  `docker stats` against the container if you have no cluster — watch it
  across a few crawl cycles under produced load, not at idle, then write the
  numbers into `values.yaml` comments.
