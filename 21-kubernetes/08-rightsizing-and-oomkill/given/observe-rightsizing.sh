#!/usr/bin/env bash
# Applies given/profile-workload.yaml into namespace t08, waits for it to
# settle, then prints kubectl top numbers for it. Use these numbers (plus
# your own margin for growth/spikes) to decide the requests/limits you write
# into src/deployment.yaml. Safe to re-run.
#
# Requires metrics-server to already be installed -- run
# given/install-metrics-server.sh first if `kubectl top nodes` doesn't work.

set -euo pipefail

CONTEXT="kind-sandbox20"
NS="t08"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl --context "$CONTEXT" create namespace "$NS" --dry-run=client -o yaml | kubectl --context "$CONTEXT" apply -f - >/dev/null

echo "Applying $SCRIPT_DIR/profile-workload.yaml into namespace $NS..."
kubectl --context "$CONTEXT" -n "$NS" apply -f "$SCRIPT_DIR/profile-workload.yaml"

echo "Waiting for deployment/profile-me rollout..."
kubectl --context "$CONTEXT" -n "$NS" rollout status deployment/profile-me --timeout=90s

echo "Letting it settle for 20s before reading metrics-server numbers..."
sleep 20

echo
echo "=== kubectl top pod (profile-me) ==="
for i in $(seq 1 10); do
  if kubectl --context "$CONTEXT" -n "$NS" top pod -l app=profile-me --containers 2>/dev/null; then
    break
  fi
  echo "metrics not ready yet, retrying..."
  sleep 5
done

echo
echo "This is what MEM_MB and CPU_BURN_THREADS actually cost at runtime --"
echo "the app's own overhead (interpreter, threads, HTTP server) sits on top"
echo "of MEM_MB, so real usage is always a bit above the raw knob value."
