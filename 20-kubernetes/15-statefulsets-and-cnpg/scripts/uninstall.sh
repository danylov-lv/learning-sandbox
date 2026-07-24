#!/usr/bin/env bash
# Removes the CloudNativePG operator and its CRDs. This is the teardown
# counterpart to install.sh -- normally NOT run by a learner working this
# task (task 15 owns the operator for the rest of the module); use it only
# when actually decommissioning the module's cluster-global CNPG install.
#
# Refuses to run while any Cluster CR still exists anywhere on the
# cluster: deleting the CRDs out from under a live Cluster would strand
# its pods/PVCs with no controller left to clean them up.
set -euo pipefail

CONTEXT="kind-sandbox20"
CNPG_VERSION="1.29.2"
MANIFEST_URL="https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.29/releases/cnpg-${CNPG_VERSION}.yaml"

remaining="$(kubectl --context "$CONTEXT" get clusters.postgresql.cnpg.io --all-namespaces --no-headers 2>/dev/null | wc -l | tr -d ' ')"
if [ "${remaining:-0}" -gt 0 ]; then
  echo "Refusing to uninstall: ${remaining} CNPG Cluster object(s) still exist cluster-wide." >&2
  echo "Delete them first (e.g. 'kubectl --context ${CONTEXT} delete cluster <name> -n <ns>')." >&2
  exit 1
fi

echo "Removing CloudNativePG operator ${CNPG_VERSION} and its CRDs..."
kubectl --context "$CONTEXT" delete -f "$MANIFEST_URL" --ignore-not-found=true --wait=true --timeout=120s

echo "CNPG operator removed."
