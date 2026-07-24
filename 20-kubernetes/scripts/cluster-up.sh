#!/usr/bin/env bash
# Create (or reuse) the sandbox20 kind cluster and install Calico.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLUSTER_NAME="sandbox20"
CALICO_VERSION="v3.29.1"
CALICO_MANIFEST="https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/calico.yaml"
CTX="kind-${CLUSTER_NAME}"

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "cluster '$CLUSTER_NAME' already exists, reusing it"
else
  echo "creating cluster '$CLUSTER_NAME'..."
  kind create cluster --name "$CLUSTER_NAME" --config "$MODULE_ROOT/cluster/kind-config.yaml"
fi

echo "installing Calico ($CALICO_VERSION)..."
kubectl --context "$CTX" apply -f "$CALICO_MANIFEST"

echo "waiting for nodes to be Ready..."
kubectl --context "$CTX" wait --for=condition=Ready nodes --all --timeout=300s

echo "waiting for calico-node DaemonSet pods to be Ready..."
kubectl --context "$CTX" -n kube-system rollout status daemonset/calico-node --timeout=300s

echo "waiting for calico-kube-controllers to be Ready..."
kubectl --context "$CTX" -n kube-system rollout status deployment/calico-kube-controllers --timeout=300s

echo
echo "=== sandbox20 cluster summary ==="
kubectl --context "$CTX" get nodes -o wide
echo
kubectl --context "$CTX" -n kube-system get pods -l k8s-app=calico-node
echo
echo "cluster '$CLUSTER_NAME' is up. context: $CTX"
echo "ingress HTTP: http://127.0.0.1:8320  ingress HTTPS: https://127.0.0.1:9320"
echo "apiserver: https://127.0.0.1:6320"
