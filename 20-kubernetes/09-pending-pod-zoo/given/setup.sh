#!/usr/bin/env bash
# Reset namespace t09, taint sandbox20-worker2 with the quarantine taint this
# task depends on, and apply the zoo. Safe to re-run any time you want a
# fresh copy of the fixture -- it always recreates the namespace from
# scratch. Only touches namespace t09 and the s20-t09/quarantine taint on
# sandbox20-worker2; nothing else in the cluster is affected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t09"

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== tainting sandbox20-worker2 (s20-t09/quarantine=true:NoSchedule) =="
kubectl --context "$CTX" taint node sandbox20-worker2 s20-t09/quarantine=true:NoSchedule --overwrite

echo "== applying the zoo =="
kubectl --context "$CTX" -n "$NS" apply -f "$SCRIPT_DIR/zoo.yaml"

echo
echo "Five pods applied, all expected to stay Pending. Start diagnosing with:"
echo "  kubectl --context $CTX -n $NS get pods"
echo "  kubectl --context $CTX -n $NS get events --sort-by=.lastTimestamp"
echo "  kubectl --context $CTX -n $NS describe pod <name>"
echo
echo "Remember: the s20-t09/quarantine taint on sandbox20-worker2 is part of"
echo "this fixture. Don't remove it yourself -- the validator (and your own"
echo "fix for pod-d) has to work with it in place."
