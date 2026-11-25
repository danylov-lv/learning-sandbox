#!/usr/bin/env bash
# Removes the metrics-server installed by install-metrics-server.sh.
# Only run this if you intentionally want to reclaim it -- every later
# task in this module (and the validator for this one) assumes
# metrics-server is installed and running.

set -euo pipefail

CONTEXT="kind-sandbox20"
VERSION="v0.7.2"
URL="https://github.com/kubernetes-sigs/metrics-server/releases/download/${VERSION}/components.yaml"

echo "Uninstalling metrics-server ${VERSION} from cluster (context ${CONTEXT})..."

curl -sL "$URL" \
  | sed 's/- --metric-resolution=15s/- --metric-resolution=15s\n        - --kubelet-insecure-tls/' \
  | kubectl --context "$CONTEXT" delete --ignore-not-found=true -f -

echo "Done."
