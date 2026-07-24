#!/usr/bin/env bash
# Reset namespaces t14 and t14-external and apply the fixture topology.
# Safe to re-run any time you want a fresh copy. Only touches these two
# namespaces; nothing else in the cluster is affected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t14"
NS_EXT="t14-external"

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== resetting namespace $NS_EXT =="
kubectl --context "$CTX" delete namespace "$NS_EXT" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS_EXT"

echo "== applying the topology =="
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/queue.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/target.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/decoy.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/worker.yaml"
kubectl --context "$CTX" -n "$NS_EXT" apply -f "$SCRIPT_DIR/outsider.yaml"

echo
echo "Waiting for rollouts..."
kubectl --context "$CTX" -n "$NS" rollout status deployment/queue --timeout=120s
kubectl --context "$CTX" -n "$NS" rollout status deployment/target --timeout=120s
kubectl --context "$CTX" -n "$NS" rollout status deployment/decoy --timeout=120s
kubectl --context "$CTX" -n "$NS" rollout status deployment/worker --timeout=120s
kubectl --context "$CTX" -n "$NS_EXT" rollout status deployment/outsider --timeout=120s

echo
echo "Topology is up. Right now (no NetworkPolicy yet) EVERYTHING can reach"
echo "everything -- that's the baseline you're locking down. worker should"
echo "end up able to reach only queue (6379) and target (8080), nothing else,"
echo "and nothing else should be able to reach worker at all."
echo
echo "Poke around with:"
echo "  kubectl --context $CTX -n $NS get pods -o wide"
echo "  kubectl --context $CTX -n $NS run probe --rm -it --restart=Never \\"
echo "    --image=sandbox20-app:1.0 --labels=app=worker --command -- \\"
echo "    python3 -c \"import socket; socket.create_connection(('decoy', 80), timeout=3)\""
