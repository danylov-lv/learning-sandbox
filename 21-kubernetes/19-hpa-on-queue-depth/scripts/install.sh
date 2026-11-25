#!/usr/bin/env bash
# Installs RabbitMQ + Prometheus + prometheus-adapter -- a cluster-global,
# owning install for the whole module (see .authoring/design.md's
# "Cluster-global installs" table). Every later task assumes this is
# already installed; do not reinstall/uninstall it from another task.
#
# Everything lives in namespace t19-infra, deliberately separate from the
# t19 namespace: the validator deletes/recreates t19 on every run, and this
# stack must survive that.
#
# Re-runnable: kubectl apply -f is idempotent, and waiting on a rollout
# that is already Ready returns immediately.
set -euo pipefail

# On Git Bash / MSYS, a bare argument like /apis/external.metrics.k8s.io
# passed to a native kubectl.exe gets rewritten as a Windows path before
# kubectl ever sees it (observed live: it became
# "C:/Program Files/Git/apis/..."). This env var disables that rewrite for
# every command below, including the `kubectl get --raw` calls this script
# and the validator both depend on.
export MSYS_NO_PATHCONV=1

CONTEXT="kind-sandbox20"
NS="t19-infra"

RABBITMQ_IMAGE="rabbitmq:3.13-management"
PROMETHEUS_IMAGE="prom/prometheus:v2.55.1"
ADAPTER_IMAGE="registry.k8s.io/prometheus-adapter/prometheus-adapter:v0.12.0"

# RabbitMQ credentials used by both the monitoring stack's own scrape and
# the fixture app's producer/consumer (given/producer.yaml, given/consumer.yaml).
# A *custom* user is required, not the default `guest` -- RabbitMQ restricts
# `guest` to loopback connections only, which would refuse every connection
# from another pod.
RABBIT_USER="sandbox"
RABBIT_PASS="sandboxpass"
QUEUE_NAME="sandbox20-queue"

echo "Installing RabbitMQ + Prometheus + prometheus-adapter (cluster-global, owned by task 19)..."
kubectl --context "$CONTEXT" create namespace "$NS" --dry-run=client -o yaml | kubectl --context "$CONTEXT" apply -f -

kubectl --context "$CONTEXT" -n "$NS" create secret generic rabbitmq-auth \
  --from-literal=username="$RABBIT_USER" \
  --from-literal=password="$RABBIT_PASS" \
  --dry-run=client -o yaml | kubectl --context "$CONTEXT" apply -f -

# --------------------------------------------------------------------
# RabbitMQ, with the rabbitmq_prometheus plugin enabled at boot via a
# mounted enabled_plugins file (overrides the image's default, so
# rabbitmq_management must be listed explicitly too or the mgmt UI/API
# stop working).
# --------------------------------------------------------------------
cat <<EOF | kubectl --context "$CONTEXT" apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: rabbitmq-plugins
  namespace: $NS
data:
  enabled_plugins: |
    [rabbitmq_management,rabbitmq_prometheus].
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rabbitmq
  namespace: $NS
  labels:
    app: rabbitmq
spec:
  replicas: 1
  selector:
    matchLabels: {app: rabbitmq}
  strategy: {type: Recreate}
  template:
    metadata:
      labels: {app: rabbitmq}
    spec:
      containers:
        - name: rabbitmq
          image: $RABBITMQ_IMAGE
          ports:
            - {containerPort: 5672, name: amqp}
            - {containerPort: 15672, name: management}
            - {containerPort: 15692, name: prom-metrics}
          env:
            - name: RABBITMQ_DEFAULT_USER
              valueFrom: {secretKeyRef: {name: rabbitmq-auth, key: username}}
            - name: RABBITMQ_DEFAULT_PASS
              valueFrom: {secretKeyRef: {name: rabbitmq-auth, key: password}}
          volumeMounts:
            - {name: plugins, mountPath: /etc/rabbitmq/enabled_plugins, subPath: enabled_plugins}
          readinessProbe:
            tcpSocket: {port: 5672}
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            tcpSocket: {port: 5672}
            initialDelaySeconds: 20
            periodSeconds: 10
          resources:
            requests: {cpu: 100m, memory: 256Mi}
            limits: {cpu: 500m, memory: 512Mi}
      volumes:
        - name: plugins
          configMap: {name: rabbitmq-plugins}
---
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq
  namespace: $NS
  labels: {app: rabbitmq}
spec:
  selector: {app: rabbitmq}
  ports:
    - {name: amqp, port: 5672, targetPort: 5672}
    - {name: management, port: 15672, targetPort: 15672}
    - {name: prom-metrics, port: 15692, targetPort: 15692}
EOF

echo "Waiting for rabbitmq to become Ready..."
kubectl --context "$CONTEXT" -n "$NS" rollout status deployment/rabbitmq --timeout=180s

# By default rabbitmq_prometheus only exposes cluster/node-aggregate
# metrics; per-queue series (rabbitmq_queue_messages_ready etc, with a
# `queue` label) require this flag. Set it via rabbitmqctl so it takes
# effect without another restart-inducing config file mount.
echo "Enabling per-object (per-queue) Prometheus metrics..."
RMQ_POD="$(kubectl --context "$CONTEXT" -n "$NS" get pod -l app=rabbitmq -o jsonpath='{.items[0].metadata.name}')"
kubectl --context "$CONTEXT" -n "$NS" exec "$RMQ_POD" -- \
  rabbitmqctl eval 'application:set_env(rabbitmq_prometheus, return_per_object_metrics, true).' >/dev/null

# Pre-declare the queue so Prometheus/the adapter have a series to scrape
# even before the fixture app's producer/consumer are up.
kubectl --context "$CONTEXT" -n "$NS" exec "$RMQ_POD" -- \
  rabbitmqadmin -u "$RABBIT_USER" -p "$RABBIT_PASS" declare queue name="$QUEUE_NAME" durable=false >/dev/null

# --------------------------------------------------------------------
# Prometheus: minimal single-Deployment install, scraping rabbitmq's
# :15692/metrics on a fixed interval. No Alertmanager, no Operator, no
# persistent storage -- this stack's only job is to feed prometheus-adapter.
# --------------------------------------------------------------------
cat <<EOF | kubectl --context "$CONTEXT" apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: $NS
data:
  prometheus.yml: |
    global:
      scrape_interval: 5s
    scrape_configs:
      - job_name: rabbitmq
        static_configs:
          - targets: ["rabbitmq.$NS.svc.cluster.local:15692"]
            # rabbitmq_prometheus's series carry no "namespace" label of
            # their own (RabbitMQ doesn't know Kubernetes namespaces
            # exist) -- this static label stands in for one, tagging the
            # series with the k8s namespace the queue's owning workload
            # (the fixture app's producer/consumer) actually lives in.
            # prometheus-adapter's external rule below maps this label to
            # the Kubernetes "namespace" resource so the external metrics
            # API can scope the query to that namespace.
            labels:
              namespace: t19
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: $NS
  labels: {app: prometheus}
spec:
  replicas: 1
  selector:
    matchLabels: {app: prometheus}
  template:
    metadata:
      labels: {app: prometheus}
    spec:
      containers:
        - name: prometheus
          image: $PROMETHEUS_IMAGE
          args:
            - --config.file=/etc/prometheus/prometheus.yml
            - --storage.tsdb.retention.time=6h
            - --web.enable-lifecycle
          ports:
            - {containerPort: 9090}
          volumeMounts:
            - {name: config, mountPath: /etc/prometheus}
          readinessProbe:
            httpGet: {path: /-/ready, port: 9090}
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests: {cpu: 100m, memory: 256Mi}
            limits: {cpu: 500m, memory: 512Mi}
      volumes:
        - name: config
          configMap: {name: prometheus-config}
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: $NS
  labels: {app: prometheus}
spec:
  selector: {app: prometheus}
  ports:
    - {name: http, port: 9090, targetPort: 9090}
EOF

echo "Waiting for prometheus to become Ready..."
kubectl --context "$CONTEXT" -n "$NS" rollout status deployment/prometheus --timeout=180s

# --------------------------------------------------------------------
# prometheus-adapter: registers the external.metrics.k8s.io/v1beta1 API,
# backed by an "external rule" that turns Prometheus's
# rabbitmq_queue_messages_ready{queue="sandbox20-queue"} series into the
# external metric `rabbitmq_queue_messages_ready`, queryable per-namespace.
# --------------------------------------------------------------------
cat <<EOF | kubectl --context "$CONTEXT" apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: adapter-config
  namespace: $NS
data:
  config.yaml: |
    externalRules:
      # Exposes rabbitmq_queue_messages_ready{queue="sandbox20-queue"} as
      # the external metric "rabbitmq_queue_messages_ready", scoped to
      # namespace t19 via the "namespace" label injected by Prometheus's
      # scrape config above. resources.overrides is what tells the
      # adapter which Prometheus label plays the role of the Kubernetes
      # "namespace" resource for this metric -- without it, a request
      # scoped to a namespace (which is how the external metrics API
      # always works, e.g. .../namespaces/t19/rabbitmq_queue_messages_ready)
      # errors with "no generic resource label form specified for this
      # metric" instead of silently ignoring the scope.
      - seriesQuery: 'rabbitmq_queue_messages_ready{queue!=""}'
        resources:
          overrides:
            namespace: {resource: "namespace"}
        name:
          matches: "rabbitmq_queue_messages_ready"
          as: "rabbitmq_queue_messages_ready"
        metricsQuery: 'sum(<<.Series>>{<<.LabelMatchers>>}) by (queue)'
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus-adapter
  namespace: $NS
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prometheus-adapter-server-resources
rules:
  - apiGroups: ["custom.metrics.k8s.io", "external.metrics.k8s.io"]
    resources: ["*"]
    verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus-adapter-hpa-controller-external
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus-adapter-server-resources
subjects:
  - kind: ServiceAccount
    name: prometheus-adapter
    namespace: $NS
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus-adapter-auth-delegator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
  - kind: ServiceAccount
    name: prometheus-adapter
    namespace: $NS
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: prometheus-adapter-auth-reader
  namespace: kube-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: extension-apiserver-authentication-reader
subjects:
  - kind: ServiceAccount
    name: prometheus-adapter
    namespace: $NS
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: system:metrics-reader
rules:
  - apiGroups: ["custom.metrics.k8s.io", "external.metrics.k8s.io"]
    resources: ["*"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: hpa-controller-external-metrics
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:metrics-reader
subjects:
  - kind: ServiceAccount
    name: horizontal-pod-autoscaler
    namespace: kube-system
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus-adapter
  namespace: $NS
  labels: {app: prometheus-adapter}
spec:
  replicas: 1
  selector:
    matchLabels: {app: prometheus-adapter}
  template:
    metadata:
      labels: {app: prometheus-adapter}
    spec:
      serviceAccountName: prometheus-adapter
      containers:
        - name: prometheus-adapter
          image: $ADAPTER_IMAGE
          args:
            - --secure-port=6443
            - --cert-dir=/tmp/cert
            - --prometheus-url=http://prometheus.$NS.svc.cluster.local:9090/
            - --metrics-relist-interval=15s
            - --config=/etc/adapter/config.yaml
          ports:
            - {containerPort: 6443}
          volumeMounts:
            - {name: config, mountPath: /etc/adapter}
            - {name: tmp, mountPath: /tmp}
          resources:
            requests: {cpu: 50m, memory: 128Mi}
            limits: {cpu: 250m, memory: 256Mi}
      volumes:
        - name: config
          configMap: {name: adapter-config}
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus-adapter
  namespace: $NS
  labels: {app: prometheus-adapter}
spec:
  selector: {app: prometheus-adapter}
  ports:
    - {port: 443, targetPort: 6443}
---
apiVersion: apiregistration.k8s.io/v1
kind: APIService
metadata:
  name: v1beta1.external.metrics.k8s.io
spec:
  service:
    name: prometheus-adapter
    namespace: $NS
    port: 443
  group: external.metrics.k8s.io
  version: v1beta1
  insecureSkipTLSVerify: true
  groupPriorityMinimum: 100
  versionPriority: 100
EOF

echo "Waiting for prometheus-adapter to become Ready..."
kubectl --context "$CONTEXT" -n "$NS" rollout status deployment/prometheus-adapter --timeout=180s

EXTERNAL_METRIC_PATH="/apis/external.metrics.k8s.io/v1beta1/namespaces/t19/rabbitmq_queue_messages_ready?labelSelector=queue%3D${QUEUE_NAME}"

echo "Waiting for the external.metrics.k8s.io API to report the queue metric..."
ok=0
for i in $(seq 1 30); do
  if kubectl --context "$CONTEXT" get --raw "$EXTERNAL_METRIC_PATH" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done
if [ "$ok" != "1" ]; then
  echo "prometheus-adapter did not start reporting the metric in time; last response:" >&2
  kubectl --context "$CONTEXT" get --raw "$EXTERNAL_METRIC_PATH" >&2 || true
  exit 1
fi

echo "RabbitMQ + Prometheus + prometheus-adapter installed in namespace $NS."
echo "Queue: $QUEUE_NAME  |  user: $RABBIT_USER  |  metric: rabbitmq_queue_messages_ready"
echo "Verify any time with:"
echo "  kubectl --context $CONTEXT get --raw '$EXTERNAL_METRIC_PATH'"
