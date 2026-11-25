#!/usr/bin/env bash
# Remove ingress-nginx from the cluster. Task 13 owns this component -- do
# not run this unless you specifically want it gone; every later task
# (14+) assumes it is installed and does not reinstall it itself.
set -euo pipefail

CTX="kind-sandbox20"
VERSION="controller-v1.12.1"
MANIFEST_URL="https://raw.githubusercontent.com/kubernetes/ingress-nginx/${VERSION}/deploy/static/provider/kind/deploy.yaml"

echo "removing ingress-nginx (${VERSION})..."
kubectl --context "$CTX" delete -f "$MANIFEST_URL" --ignore-not-found=true --wait=true --timeout=120s
echo "done."
