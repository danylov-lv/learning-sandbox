# Hint 3

**Dependency block** (goes in `chart/Chart.yaml`, replacing the empty
`dependencies: []`):

```yaml
dependencies:
  - name: queue-chart
    version: "0.1.0"
    repository: "file://../given/queue-chart"
    condition: queue.enabled
```

Then, from inside `chart/`: `helm dependency build`.

**Worker env block**, guarded against `queue.enabled: false`:

```yaml
env:
  - name: WORK_MODE
    value: "consumer"
  - name: QUEUE_BACKEND
    value: "redis"
  {{- if .Values.queue.enabled }}
  - name: REDIS_HOST
    value: {{ include "queue-chart.fullname" . }}
  - name: REDIS_PORT
    value: "6379"
  - name: QUEUE_KEY
    value: {{ .Values.queue.key | quote }}
  {{- end }}
```

**Hook Job**, same guard wrapping the whole manifest:

```yaml
{{- if .Values.queue.enabled }}
apiVersion: batch/v1
kind: Job
metadata:
  name: queue-init
  annotations:
    "helm.sh/hook": pre-install,pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: queue-init
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: IfNotPresent
          command: [python3, -c, "<your script>"]
          env:
            - name: REDIS_HOST
              value: {{ include "queue-chart.fullname" . }}
            - name: REDIS_PORT
              value: "6379"
            - name: QUEUE_KEY
              value: {{ .Values.queue.key | quote }}
            - name: SEED_COUNT
              value: {{ .Values.queue.seedCount | quote }}
{{- end }}
```

Your seed script (the `<your script>` above) needs to, in order: connect to
`redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT))`, retry `.ping()` in a
short loop (redis's own pod may still be starting even though it's a
lower-weight hook -- a few attempts a second or two apart is enough), then
`RPUSH` `SEED_COUNT` items onto the list named `QUEUE_KEY`. That's the
whole job -- write it as a short inline script or a heredoc-style
multi-line `command`, your choice.

**Diff commands**, run for real from `chart/`:

```bash
helm template t05-stack . -f values.yaml -f values-dev.yaml  > /tmp/dev.out
helm template t05-stack . -f values.yaml -f values-prod.yaml > /tmp/prod.out
diff /tmp/dev.out /tmp/prod.out
```

Whatever `diff` actually prints is what goes in `DIFF.md`'s "Differences
found" section -- replicas, the resources block, and `QUEUE_KEY` should all
show up as changed lines if `values-dev.yaml`/`values-prod.yaml` are wired
correctly.
