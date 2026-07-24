#!/usr/bin/env bash
# Reset namespace t10 and apply the broken fixture. Safe to re-run any time
# you want a fresh copy -- always recreates the namespace from scratch.
# Only touches namespace t10; nothing else in the cluster is affected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t10"

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== applying the broken fixture =="
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/broken.yaml"

echo
echo "Two Deployments (ingest, render) and one standalone debug Pod applied."
echo "Expect: ingest crash-looping, render stuck NotReady, render-debug-target"
echo "Running/Ready (it has no probe -- it's just a stable target to attach"
echo "ephemeral debug containers to)."
echo
echo "Start diagnosing with:"
echo "  kubectl --context $CTX -n $NS get pods"
echo "  kubectl --context $CTX -n $NS logs deploy/ingest --previous"
echo "  kubectl --context $CTX -n $NS describe pod -l app=render"
echo "  kubectl --context $CTX -n $NS debug -it render-debug-target --image=sandbox20-app:1.0 --target=render -- sh"
