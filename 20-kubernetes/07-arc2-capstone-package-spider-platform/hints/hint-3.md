# Hint 3

Rough shape, still incomplete -- fill in every real value/indent yourself.

**`_helpers.tpl`** -- the standard `helm create` scaffold, unmodified
except for the chart name:

```
{{- define "spider-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "spider-platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "spider-platform.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "spider-platform.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "spider-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "spider-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
```

Add one more small helper that takes a component name as `.` context (or
just repeat one extra line at each call site) so every template can emit
`app.kubernetes.io/component: <name>` alongside the two blocks above.

**`queue-service.yaml`** (the name every other component's `REDIS_HOST`
must match):

```
apiVersion: v1
kind: Service
metadata:
  name: {{ include "spider-platform.fullname" . }}-queue
  labels:
    {{- include "spider-platform.labels" . | nindent 4 }}
    app.kubernetes.io/component: queue
spec:
  selector:
    {{- include "spider-platform.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: queue
  ports:
    - port: {{ .Values.queue.port }}
      targetPort: {{ .Values.queue.port }}
```

**`producer-deployment.yaml`**'s env block (the part that actually
matters -- surrounding Deployment boilerplate omitted, same shape as
`queue`'s but with `{{ if .Values.producer.enabled }}` wrapping the
document and `spec.replicas: {{ .Values.producer.replicas }}`):

```
env:
  - name: WORK_MODE
    value: "producer"
  - name: QUEUE_BACKEND
    value: "redis"
  - name: REDIS_HOST
    value: "{{ include "spider-platform.fullname" . }}-queue"
  - name: REDIS_PORT
    value: "{{ .Values.queue.port }}"
  - name: QUEUE_KEY
    value: "{{ .Values.queue.key }}"
  - name: RATE_PER_S
    value: "{{ .Values.producer.ratePerS }}"
```

**`workers-configmap.yaml`** + the checksum annotation on
**`workers-deployment.yaml`**:

```
# workers-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "spider-platform.fullname" . }}-workers-config
  labels:
    {{- include "spider-platform.labels" . | nindent 4 }}
    app.kubernetes.io/component: workers
data:
  WORK_MODE: "consumer"
  QUEUE_BACKEND: "redis"
  REDIS_HOST: "{{ include "spider-platform.fullname" . }}-queue"
  REDIS_PORT: "{{ .Values.queue.port }}"
  QUEUE_KEY: "{{ .Values.queue.key }}"
  PROCESS_MS: "{{ .Values.workers.processMs }}"
```

```
# workers-deployment.yaml, pod template section only
template:
  metadata:
    labels:
      {{- include "spider-platform.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: workers
    annotations:
      checksum/config: {{ include (print $.Template.BasePath "/workers-configmap.yaml") . | sha256sum }}
  spec:
    containers:
      - name: workers
        image: "{{ .Values.workers.image.repository }}:{{ .Values.workers.image.tag }}"
        imagePullPolicy: {{ .Values.workers.image.pullPolicy }}
        envFrom:
          - configMapRef:
              name: {{ include "spider-platform.fullname" . }}-workers-config
        resources:
          {{- toYaml .Values.workers.resources | nindent 10 }}
        readinessProbe:
          httpGet:
            path: {{ .Values.workers.probes.readiness.path }}
            port: {{ .Values.workers.probes.readiness.port }}
          initialDelaySeconds: {{ .Values.workers.probes.readiness.initialDelaySeconds }}
          periodSeconds: {{ .Values.workers.probes.readiness.periodSeconds }}
          timeoutSeconds: {{ .Values.workers.probes.readiness.timeoutSeconds }}
          failureThreshold: {{ .Values.workers.probes.readiness.failureThreshold }}
```

**`values-dev.yaml`** / **`values-prod.yaml`** numbers -- pick your own,
but sanity-check the arithmetic before you commit to them: with
`workers.processMs: 200` and `workers.replicas: 1`, one worker drains
`1000/200 = 5` items/s, so `producer.ratePerS: 2` in dev leaves 3/s of
headroom. Scaling to `workers.replicas: 3` at `workers.processMs: 150`
gives `3 * (1000/150) ≈ 20` items/s of capacity, so a prod
`producer.ratePerS` anywhere up to high single digits still drains
cleanly with headroom to spare.

**Sanity-check order**: `helm lint chart/`, then `helm template
release-name chart/ | less` and read every rendered document by eye before
you ever try `helm install` against the live cluster.
