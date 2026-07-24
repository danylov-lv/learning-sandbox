#!/usr/bin/env bash
# Install ingress-nginx into the sandbox20 kind cluster. This component is
# OWNED by task 13 (see .authoring/design.md's "Cluster-global installs"
# table) -- every later task assumes it is already installed and must not
# reinstall or uninstall it. Re-runnable: kubectl apply is idempotent, and
# every wait below tolerates an already-Ready controller from a prior run.
set -euo pipefail

CTX="kind-sandbox20"
VERSION="controller-v1.12.1"
MANIFEST_URL="https://raw.githubusercontent.com/kubernetes/ingress-nginx/${VERSION}/deploy/static/provider/kind/deploy.yaml"

# The "kind" provider variant (as opposed to "baremetal"/"cloud") patches the
# controller Deployment with nodeSelector ingress-ready=true and hostPort
# 80/443 -- this is what makes it bind onto the control-plane node that
# cluster/kind-config.yaml maps to host ports 8320/9320.
echo "installing ingress-nginx (${VERSION}) for kind..."
kubectl --context "$CTX" apply -f "$MANIFEST_URL"

# The admission-create/admission-patch Jobs run with ttlSecondsAfterFinished:
# 0, so they can disappear before a `kubectl wait` on them ever observes
# "complete" -- there's nothing stable to poll. Waiting on the controller
# rollout below is what actually matters and is race-free.
echo "waiting for the controller rollout..."
kubectl --context "$CTX" -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=180s

echo
echo "ingress-nginx controller is Ready."
echo "  HTTP:  http://127.0.0.1:8320"
echo "  HTTPS: https://127.0.0.1:9320"
echo "  IngressClass: nginx (kubectl --context $CTX get ingressclass)"
