#!/usr/bin/env bash
# Reset namespace t11 and apply the broken pipeline fresh. Safe to re-run
# any time you want to go back to the seeded incident -- it always
# recreates the namespace from scratch. Only touches namespace t11;
# nothing else in the cluster is affected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t11"

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== applying the pipeline (redis, pipeline-config, api, worker, producer) =="
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/redis.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/pipeline-config.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/api.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/worker.yaml"
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/producer.yaml"

echo
echo "Give it 30-60s, then start triaging with:"
echo "  kubectl --context $CTX -n $NS get pods"
echo "  kubectl --context $CTX -n $NS get events --sort-by=.lastTimestamp"
echo "  kubectl --context $CTX -n $NS logs deploy/api --previous"
echo "  kubectl --context $CTX -n $NS logs deploy/worker --previous"
echo
echo "Something in this pipeline is down, and something else looks fine but"
echo "isn't doing its job. Find the one thing they have in common."
