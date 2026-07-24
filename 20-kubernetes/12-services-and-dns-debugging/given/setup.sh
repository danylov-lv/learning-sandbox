#!/usr/bin/env bash
# Reset namespace t12 and apply the broken fixture. Safe to re-run any time
# you want a fresh copy -- always recreates the namespace from scratch.
# Only touches namespace t12; nothing else in the cluster is affected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t12"

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== applying the broken fixture =="
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/broken.yaml"

echo
echo "One healthy Deployment (catalog-backend) and three broken Services"
echo "(catalog, catalog-batch, catalog-peer) applied. catalog-backend's pods"
echo "should reach Ready on their own -- the problem is in the Service"
echo "wiring, not the app."
echo
echo "Start diagnosing with:"
echo "  kubectl --context $CTX -n $NS get pods -o wide"
echo "  kubectl --context $CTX -n $NS get endpoints"
echo "  kubectl --context $CTX -n $NS describe svc catalog catalog-batch catalog-peer"
echo "  kubectl --context $CTX -n $NS run dnsprobe --image=sandbox20-app:1.0 --image-pull-policy=IfNotPresent --restart=Never --command -- sleep 300"
echo "  kubectl --context $CTX -n $NS exec dnsprobe -- python3 -c \"import socket; print(socket.gethostbyname('catalog.$NS.svc.cluster.local'))\""
