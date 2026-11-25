#!/usr/bin/env bash
# Reset namespace t20 and apply the `web` fleet fresh. Safe to re-run any
# time you want a clean 4-replica deployment. Only touches namespace t20.
# The validator drains a worker node during grading and always uncordons
# every node afterward -- this setup script never touches node state.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t20"
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/deployment.yaml"
echo
echo "web Deployment (4 replicas, soft-spread across the two workers) applied into $NS."
echo "Inspect the spread with:"
echo "  kubectl --context $CTX -n $NS get pods -o wide"
