#!/usr/bin/env bash
# Installs metrics-server (cluster-global, shared by every task in this
# module -- see .authoring/design.md's "Cluster-global installs" table).
# Owned by task 08. Do not reinstall it from any other task.
#
# Pinned version: v0.7.2
# Source: https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
#
# kind's kubelets serve kubelet-metrics over a certificate metrics-server
# doesn't trust by default, so the stock manifest is patched with
# --kubelet-insecure-tls -- the standard recipe for any kind-based cluster,
# not something specific to this module.
#
# Idempotent: safe to re-run; kubectl apply is declarative and this script
# waits until `kubectl top nodes` actually returns numbers before exiting.

set -euo pipefail

CONTEXT="kind-sandbox20"
VERSION="v0.7.2"
URL="https://github.com/kubernetes-sigs/metrics-server/releases/download/${VERSION}/components.yaml"

echo "Installing metrics-server ${VERSION} into cluster (context ${CONTEXT})..."

curl -sL "$URL" \
  | sed 's/- --metric-resolution=15s/- --metric-resolution=15s\n        - --kubelet-insecure-tls/' \
  | kubectl --context "$CONTEXT" apply -f -

echo "Waiting for metrics-server Deployment to become available..."
kubectl --context "$CONTEXT" -n kube-system rollout status deployment/metrics-server --timeout=120s

echo "Waiting for the metrics API to start serving numbers (this takes a bit after rollout)..."
for i in $(seq 1 30); do
  if kubectl --context "$CONTEXT" top nodes >/dev/null 2>&1; then
    echo "metrics-server is serving. kubectl top nodes:"
    kubectl --context "$CONTEXT" top nodes
    exit 0
  fi
  sleep 5
done

echo "metrics-server did not start serving metrics within 150s -- check 'kubectl --context ${CONTEXT} -n kube-system logs deploy/metrics-server'" >&2
exit 1
