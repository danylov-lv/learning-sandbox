#!/usr/bin/env bash
# Tears down the cluster-global RabbitMQ + Prometheus + prometheus-adapter
# install (see scripts/install.sh). Do NOT run this unless you specifically
# want to remove infrastructure other tasks in this module do not depend
# on -- nothing else in the module uses this stack, but it is still an
# owning install and should be torn down deliberately, not as a side effect.
set -euo pipefail

CONTEXT="kind-sandbox20"
NS="t19-infra"

echo "Removing prometheus-adapter APIService and cluster-scoped RBAC..."
kubectl --context "$CONTEXT" delete apiservice v1beta1.external.metrics.k8s.io --ignore-not-found=true
kubectl --context "$CONTEXT" delete clusterrole prometheus-adapter-server-resources system:metrics-reader --ignore-not-found=true
kubectl --context "$CONTEXT" delete clusterrolebinding prometheus-adapter-hpa-controller-external prometheus-adapter-auth-delegator hpa-controller-external-metrics --ignore-not-found=true
kubectl --context "$CONTEXT" -n kube-system delete rolebinding prometheus-adapter-auth-reader --ignore-not-found=true

echo "Deleting namespace $NS (rabbitmq, prometheus, prometheus-adapter)..."
kubectl --context "$CONTEXT" delete namespace "$NS" --ignore-not-found=true --wait=false

echo "Uninstall requested. Namespace deletion continues in the background;"
echo "check with: kubectl --context $CONTEXT get ns $NS"
