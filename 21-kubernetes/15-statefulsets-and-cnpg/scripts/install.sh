#!/usr/bin/env bash
# Installs the CloudNativePG (CNPG) operator -- a cluster-global,
# owning install for the whole module (see .authoring/design.md's
# "Cluster-global installs" table). Every later task assumes this is
# already installed; do not reinstall/uninstall it from another task.
#
# Re-runnable: `kubectl apply -f` on the same manifest is idempotent, and
# waiting on a rollout that is already Ready returns immediately.
set -euo pipefail

CONTEXT="kind-sandbox20"
CNPG_VERSION="1.29.2"
# CNPG 1.29.x officially supports Kubernetes 1.33-1.35 and is tested
# (though not "officially supported") against 1.32/1.31/1.30/1.36 -- this
# cluster runs Kubernetes v1.32.2 (see cluster/kind-config.yaml), and this
# exact manifest was verified to install and run a Cluster cleanly against
# it (see .authoring/notes-t15.md). The 1.29 branch was chosen over the
# newer 1.30.x (which only tests, but does not support, 1.32) and over the
# older 1.28.x (which supports 1.32 but reached end-of-life on 2026-06-30)
# specifically to land on a branch that is both actively maintained and a
# good match for this cluster's Kubernetes version.
MANIFEST_URL="https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.29/releases/cnpg-${CNPG_VERSION}.yaml"

echo "Installing CloudNativePG operator ${CNPG_VERSION} (cluster-global, owned by task 15)..."
# Server-side apply, not client-side: a couple of these CRDs (Cluster,
# Pooler) carry a schema large enough that client-side `kubectl apply`'s
# last-applied-configuration annotation blows past the 262144-byte
# annotation limit ("metadata.annotations: Too long"). Server-side apply
# doesn't need that annotation and is still idempotent to re-run.
kubectl --context "$CONTEXT" apply --server-side --force-conflicts -f "$MANIFEST_URL"

echo "Waiting for cnpg-controller-manager to become Ready..."
kubectl --context "$CONTEXT" -n cnpg-system rollout status deployment/cnpg-controller-manager --timeout=180s

echo "CNPG operator ${CNPG_VERSION} installed and ready in namespace cnpg-system."
