#!/usr/bin/env bash
# Build the fixture app's three images and load them into the sandbox20 kind cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$MODULE_ROOT/app"
CLUSTER_NAME="sandbox20"

echo "building sandbox20-app:1.0 (APP_VERSION=1.0)..."
docker build --build-arg APP_VERSION=1.0 -t sandbox20-app:1.0 -f "$APP_DIR/Dockerfile" "$APP_DIR"

echo "building sandbox20-app:2.0 (APP_VERSION=2.0)..."
docker build --build-arg APP_VERSION=2.0 -t sandbox20-app:2.0 -f "$APP_DIR/Dockerfile" "$APP_DIR"

echo "building sandbox20-app:distroless..."
docker build --build-arg APP_VERSION=distroless -t sandbox20-app:distroless -f "$APP_DIR/Dockerfile.distroless" "$APP_DIR"

for tag in 1.0 2.0 distroless; do
  echo "loading sandbox20-app:$tag into cluster '$CLUSTER_NAME'..."
  kind load docker-image "sandbox20-app:$tag" --name "$CLUSTER_NAME"
done

# Task 11 (arc3 incident) needs a redis image inside the cluster. Plain
# redis:7-alpine ships as a multi-platform manifest list whose provenance
# attestation entry `kind load` cannot import into containerd on this setup,
# so we produce a single-platform repack (bit-identical redis layer) and
# load that. `docker build FROM redis:7-alpine` pulls the base if missing.
echo "building redis:t11-repack (single-platform repack of redis:7-alpine)..."
echo "FROM redis:7-alpine" | docker build --provenance=false --sbom=false -t redis:t11-repack -f - "$APP_DIR"
echo "loading redis:t11-repack into cluster '$CLUSTER_NAME'..."
kind load docker-image "redis:t11-repack" --name "$CLUSTER_NAME"

echo "images built and loaded: sandbox20-app:1.0, sandbox20-app:2.0, sandbox20-app:distroless, redis:t11-repack"
