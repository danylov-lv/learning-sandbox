#!/usr/bin/env bash
# Apply the broken fixture, drive continuous load through the Service while
# rolling the image from 1.0 -> 2.0, and print what actually happened:
# restart counts and request success/failure counts. Run this FIRST, before
# touching src/deployment.yaml, so you've actually seen the outage this task
# is about instead of taking it on faith.
#
# Uses only namespace t02. Safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="kind-sandbox20"
NS="t02"
LOAD_DURATION_S=60

kctl() { kubectl --context "$CTX" -n "$NS" "$@"; }

echo "== resetting namespace $NS =="
kubectl --context "$CTX" delete namespace "$NS" --ignore-not-found=true --wait=true --timeout=120s
kubectl --context "$CTX" create namespace "$NS"

echo "== applying the broken fixture =="
kctl apply -f "$SCRIPT_DIR/service.yaml"
kctl apply -f "$SCRIPT_DIR/broken-deployment.yaml"

echo "== giving it 20s to settle (watch for restarts already) =="
sleep 20
kctl get pods -o wide

echo "== starting an in-cluster load generator against the Service =="
LOAD_SCRIPT=$(cat <<PYEOF
import time, urllib.request

ok = 0
fail = 0
examples = []
url = "http://web.${NS}.svc.cluster.local/work?ms=20"
deadline = time.monotonic() + ${LOAD_DURATION_S}
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if 200 <= resp.status < 300:
                ok += 1
            else:
                fail += 1
                if len(examples) < 5:
                    examples.append("status=" + str(resp.status))
    except Exception as e:
        fail += 1
        if len(examples) < 5:
            examples.append(str(e))
    time.sleep(0.05)

print("RESULT ok=" + str(ok) + " fail=" + str(fail))
for ex in examples:
    print("EXAMPLE " + ex)
PYEOF
)

kctl delete pod loadgen --ignore-not-found=true --now >/dev/null 2>&1 || true
kctl run loadgen --image=sandbox20-app:1.0 --image-pull-policy=Never --restart=Never \
  --command -- python3 -c "$LOAD_SCRIPT"

echo "== triggering the rollout to sandbox20-app:2.0 while load runs =="
sleep 5
kctl set image deployment/web web=sandbox20-app:2.0
# The broken probes may prevent this from ever converging -- that's the
# point. Don't hard-fail this script if it times out; keep collecting
# evidence instead.
kctl rollout status deployment/web --timeout=60s || echo "(rollout did not converge in time -- see why below)"

echo "== waiting for the load generator to finish (~${LOAD_DURATION_S}s) =="
for _ in $(seq 1 30); do
  phase="$(kctl get pod loadgen -o jsonpath='{.status.phase}' 2>/dev/null || echo '')"
  if [ "$phase" = "Succeeded" ] || [ "$phase" = "Failed" ]; then
    break
  fi
  sleep 5
done

echo
echo "== load generator result =="
kctl logs pod/loadgen || true

echo
echo "== restart counts =="
kctl get pods -l app=web -o custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount

echo
echo "That's the outage: dropped requests and/or a restart storm caused by"
echo "missing/over-aggressive probes on a slow-starting app. Now go fix"
echo "src/deployment.yaml so this contract holds instead: kubectl set image"
echo "to :2.0 under continuous load, zero failed requests, no restarts."
