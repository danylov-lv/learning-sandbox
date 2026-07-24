#!/usr/bin/env bash
# Tear down the sandbox20 kind cluster.
set -euo pipefail

CLUSTER_NAME="sandbox20"

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  kind delete cluster --name "$CLUSTER_NAME"
  echo "cluster '$CLUSTER_NAME' deleted"
else
  echo "cluster '$CLUSTER_NAME' does not exist, nothing to do"
fi
