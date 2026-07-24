#!/usr/bin/env bash
# Installs Argo CD + an in-cluster Gitea git server -- cluster-global,
# OWNING install for the whole module (see .authoring/design.md's
# "Cluster-global installs" table). Tasks 17 and 18 assume both stay
# installed; do not reinstall/uninstall them from another task.
#
# Re-runnable: kubectl apply is idempotent, every wait tolerates an
# already-Ready component from a prior run, and the Gitea seeding step
# checks before it creates (repo push is force-pushed so it converges
# either way).
set -euo pipefail

CTX="kind-sandbox20"
ARGOCD_VERSION="v3.4.5"
ARGOCD_MANIFEST_URL="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
GITEA_IMAGE="gitea/gitea:1.24.7"

TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITEA_MANIFEST="${TASK_ROOT}/given/gitea/gitea.yaml"
CHART_DIR="${TASK_ROOT}/given/chart"

GITEA_ORG="sandbox20"
GITEA_REPO="platform-charts"
GITEA_ADMIN_USER="gitea-admin"
GITEA_ADMIN_PASSWORD="sandbox20-gitea-admin-pw"
# Documented, in-cluster repo URL + chart path the learner's Application
# (src/application.yaml) must point at. Keep this in sync with README.md
# and tests/validate.py if it ever changes.
REPO_URL="http://gitea-http.argocd.svc.cluster.local:3000/${GITEA_ORG}/${GITEA_REPO}.git"
CHART_PATH="."

echo "== 1/5: namespace + Argo CD (${ARGOCD_VERSION}) =="
kubectl --context "$CTX" create namespace argocd --dry-run=client -o yaml | kubectl --context "$CTX" apply -f -
# Server-side apply: the Application/AppProject/ApplicationSet CRDs are
# large enough that client-side apply's last-applied-configuration
# annotation can blow past the 262144-byte limit (same reason task 15
# uses --server-side for CNPG's CRDs).
kubectl --context "$CTX" apply --server-side --force-conflicts -n argocd -f "$ARGOCD_MANIFEST_URL"

echo "waiting for argocd-server, argocd-repo-server, argocd-application-controller..."
kubectl --context "$CTX" -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl --context "$CTX" -n argocd rollout status deployment/argocd-repo-server --timeout=300s
kubectl --context "$CTX" -n argocd rollout status statefulset/argocd-application-controller --timeout=300s

echo "== 2/5: Gitea (${GITEA_IMAGE}) =="
kubectl --context "$CTX" apply -f "$GITEA_MANIFEST"
kubectl --context "$CTX" -n argocd rollout status deployment/gitea --timeout=300s

echo "== 3/5: seeding Gitea admin user =="
GITEA_POD="$(kubectl --context "$CTX" -n argocd get pod -l app.kubernetes.io/name=gitea -o jsonpath='{.items[0].metadata.name}')"
if ! kubectl --context "$CTX" -n argocd exec "$GITEA_POD" -- \
    gitea admin user list --admin 2>/dev/null | grep -q "$GITEA_ADMIN_USER"; then
  kubectl --context "$CTX" -n argocd exec "$GITEA_POD" -- \
    gitea admin user create \
      --username "$GITEA_ADMIN_USER" \
      --password "$GITEA_ADMIN_PASSWORD" \
      --email "${GITEA_ADMIN_USER}@sandbox20.test" \
      --admin --must-change-password=false
else
  echo "admin user '${GITEA_ADMIN_USER}' already exists, skipping."
fi

echo "== 4/5: creating org/repo + pushing the fixture chart =="
LOCAL_PORT=39000
pkill -f "port-forward svc/gitea-http ${LOCAL_PORT}:3000" 2>/dev/null || true
kubectl --context "$CTX" -n argocd port-forward svc/gitea-http "${LOCAL_PORT}:3000" >/tmp/t16-gitea-pf.log 2>&1 &
PF_PID=$!
WORKDIR=""
cleanup() {
  kill "$PF_PID" 2>/dev/null || true
  [ -n "$WORKDIR" ] && rm -rf "$WORKDIR"
}
trap cleanup EXIT

echo "waiting for the port-forward to connect..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${LOCAL_PORT}/api/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

GITEA_API="http://${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASSWORD}@127.0.0.1:${LOCAL_PORT}/api/v1"

if ! curl -sf "http://127.0.0.1:${LOCAL_PORT}/api/v1/orgs/${GITEA_ORG}" \
    -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASSWORD}" >/dev/null 2>&1; then
  curl -sf -X POST "${GITEA_API}/orgs" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${GITEA_ORG}\"}" >/dev/null
else
  echo "org '${GITEA_ORG}' already exists, skipping."
fi

if ! curl -sf "http://127.0.0.1:${LOCAL_PORT}/api/v1/repos/${GITEA_ORG}/${GITEA_REPO}" \
    -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASSWORD}" >/dev/null 2>&1; then
  curl -sf -X POST "${GITEA_API}/orgs/${GITEA_ORG}/repos" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${GITEA_REPO}\",\"private\":false,\"auto_init\":false}" >/dev/null
else
  echo "repo '${GITEA_ORG}/${GITEA_REPO}' already exists, skipping create."
fi

WORKDIR="$(mktemp -d)"
cp -r "$CHART_DIR"/. "$WORKDIR/"
git -C "$WORKDIR" init -q -b main
git -C "$WORKDIR" add -A
git -C "$WORKDIR" -c user.email="install-script@sandbox20.test" -c user.name="sandbox20 install script" \
  commit -q -m "seed: sandbox20-fixture chart for task 16"
git -C "$WORKDIR" push -q -f \
  "http://${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASSWORD}@127.0.0.1:${LOCAL_PORT}/${GITEA_ORG}/${GITEA_REPO}.git" \
  main:main

cleanup
trap - EXIT

echo "== 5/5: done =="
ADMIN_PW="$(kubectl --context "$CTX" -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"

cat <<EOF

Argo CD ${ARGOCD_VERSION} + Gitea (${GITEA_IMAGE}) are installed and ready.

Argo CD UI / API:
  kubectl --context ${CTX} -n argocd port-forward svc/argocd-server 8080:443
  open https://127.0.0.1:8080 (self-signed cert -- accept the warning)
  user: admin
EOF
if [ -n "$ADMIN_PW" ]; then
  echo "  password: ${ADMIN_PW}"
else
  echo "  password: (argocd-initial-admin-secret not found -- it was probably already deleted after a previous login; if you never changed it, re-run this script after 'kubectl -n argocd delete secret argocd-initial-admin-secret' is NOT an option here -- ask whoever set up this cluster)"
fi
cat <<EOF

Gitea UI:
  kubectl --context ${CTX} -n argocd port-forward svc/gitea-http 3000:3000
  open http://127.0.0.1:3000
  user: ${GITEA_ADMIN_USER}
  password: ${GITEA_ADMIN_PASSWORD}

Seeded repo (this is the contract your src/application.yaml must target):
  repoURL: ${REPO_URL}
  path:    ${CHART_PATH}
  targetRevision: main
EOF
