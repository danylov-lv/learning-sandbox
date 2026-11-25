#!/usr/bin/env bash
# Applies given/leak-pod.yaml into namespace t08, waits for it to die, then
# prints the evidence you need for NOTES.md: the container's exit code,
# termination reason, and how long it survived. Safe to re-run any number of
# times -- it deletes any previous leak-victim pod first.
#
# This does not touch t01-t07/t09+ namespaces and does not install/uninstall
# anything cluster-global.

set -euo pipefail

CONTEXT="kind-sandbox20"
NS="t08"
POD="leak-victim"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl --context "$CONTEXT" create namespace "$NS" --dry-run=client -o yaml | kubectl --context "$CONTEXT" apply -f - >/dev/null

kubectl --context "$CONTEXT" -n "$NS" delete pod "$POD" --ignore-not-found=true --wait=true >/dev/null

echo "Applying $SCRIPT_DIR/leak-pod.yaml into namespace $NS..."
kubectl --context "$CONTEXT" -n "$NS" apply -f "$SCRIPT_DIR/leak-pod.yaml"

echo "Waiting for pod/$POD to terminate (this takes roughly 20-30s)..."
for i in $(seq 1 60); do
  phase=$(kubectl --context "$CONTEXT" -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  if [[ "$phase" == "Failed" || "$phase" == "Succeeded" ]]; then
    break
  fi
  sleep 2
done

echo
echo "=== pod status ==="
kubectl --context "$CONTEXT" -n "$NS" get pod "$POD" -o wide

echo
echo "=== container termination detail ==="
kubectl --context "$CONTEXT" -n "$NS" get pod "$POD" \
  -o jsonpath='exitCode={.status.containerStatuses[0].state.terminated.exitCode}{"\n"}reason={.status.containerStatuses[0].state.terminated.reason}{"\n"}startedAt={.status.containerStatuses[0].state.terminated.startedAt}{"\n"}finishedAt={.status.containerStatuses[0].state.terminated.finishedAt}{"\n"}'

echo
echo "Read hint-3.md and NOTES.md before deciding what this output means."
