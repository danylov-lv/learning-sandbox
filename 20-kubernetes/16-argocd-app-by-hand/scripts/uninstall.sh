#!/usr/bin/env bash
# Removes Argo CD + Gitea from the cluster. Task 16 owns these -- do not
# run this unless you specifically want them gone; tasks 17 and 18 assume
# both are installed and do not reinstall them themselves.
set -euo pipefail

CTX="kind-sandbox20"
ARGOCD_VERSION="v3.4.5"
ARGOCD_MANIFEST_URL="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITEA_MANIFEST="${TASK_ROOT}/given/gitea/gitea.yaml"

echo "removing Gitea..."
kubectl --context "$CTX" delete -f "$GITEA_MANIFEST" --ignore-not-found=true --wait=true --timeout=120s

echo "removing Argo CD (${ARGOCD_VERSION})..."
kubectl --context "$CTX" delete -n argocd -f "$ARGOCD_MANIFEST_URL" --ignore-not-found=true --wait=true --timeout=180s

echo "removing namespace argocd..."
kubectl --context "$CTX" delete namespace argocd --ignore-not-found=true --wait=true --timeout=180s

echo "done."
