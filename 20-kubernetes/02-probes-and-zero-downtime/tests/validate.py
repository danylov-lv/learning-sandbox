"""Validator for 20-kubernetes task 02 (probes-and-zero-downtime).

Run from this task directory:

    uv run python tests/validate.py

Recreates namespace t02, applies given/service.yaml + the learner's
src/deployment.yaml (expected to start at image sandbox20-app:1.0, same as
given/broken-deployment.yaml), waits for the initial rollout, then runs a
handful of structural anti-cheat checks against the live Deployment object.
It then starts an in-cluster load generator pod that hammers the Service
over its ClusterIP DNS name for a fixed duration, triggers `kubectl set
image` to sandbox20-app:2.0 partway through that window, waits for the
rollout to complete, and finally asserts the load generator saw zero failed
requests, every pod ended up on 2.0, and no container restarted.

Namespace t02 is deleted (best-effort, non-blocking) whether this passes or
fails.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    delete_ns,
    ensure_ns,
    guarded,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    require_cluster,
    wait_rollout,
    wait_until,
)

NS = "t02"
GIVEN_DIR = TASK_ROOT / "given"
SRC_DEPLOYMENT = TASK_ROOT / "src" / "deployment.yaml"

# How long the in-cluster load generator hammers the Service for. Must
# comfortably outlast the rollout (3 replicas, one at a time surged in under
# maxSurge>=1/maxUnavailable=0): empirically a full rollout of this fixture
# takes ~40-70s (8s START_DELAY_S per new pod + probe/detection overhead x3
# sequential steps). 150s of load gives generous margin either side.
LOAD_DURATION_S = 150
LOAD_REQUEST_INTERVAL_S = 0.05
LOAD_MIN_OK = 200

INITIAL_ROLLOUT_TIMEOUT_S = 180
ROLLING_UPDATE_TIMEOUT_S = 180
LOADGEN_WAIT_TIMEOUT_S = LOAD_DURATION_S + 90

LOAD_SCRIPT = f"""
import time, urllib.request

ok = 0
fail = 0
examples = []
url = "http://web.{NS}.svc.cluster.local/work?ms=20"
deadline = time.monotonic() + {LOAD_DURATION_S}
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if 200 <= resp.status < 300:
                ok += 1
            else:
                fail += 1
                if len(examples) < 8:
                    examples.append("status=" + str(resp.status))
    except Exception as e:
        fail += 1
        if len(examples) < 8:
            examples.append(str(e))
    time.sleep({LOAD_REQUEST_INTERVAL_S})

print("RESULT ok=" + str(ok) + " fail=" + str(fail))
for ex in examples:
    print("EXAMPLE " + ex)
"""


def _apply_given_and_learner():
    if not SRC_DEPLOYMENT.exists():
        not_passed(f"missing {SRC_DEPLOYMENT}")
    kubectl("apply", "-f", str(GIVEN_DIR / "service.yaml"), ns=NS)
    kubectl("apply", "-f", str(SRC_DEPLOYMENT), ns=NS)


def _get_live_deployment():
    return kubectl_json("get", "deployment", "web", ns=NS)


def _env_map(container: dict) -> dict:
    return {e.get("name"): e.get("value") for e in container.get("env", []) if "name" in e}


def _check_anti_cheat(dep: dict):
    spec = dep.get("spec", {})
    template = spec.get("template", {})
    containers = template.get("spec", {}).get("containers", [])
    if not containers:
        not_passed("learner Deployment has no containers")
    c = containers[0]

    env = _env_map(c)
    if env.get("START_DELAY_S") != "8":
        not_passed(
            f"env START_DELAY_S must stay '8' (the slow-start fixture this task is about) -- "
            f"found {env.get('START_DELAY_S')!r}"
        )

    readiness = c.get("readinessProbe")
    if not readiness:
        not_passed("no readinessProbe on the web container")
    r_path = readiness.get("httpGet", {}).get("path")
    if r_path != "/readyz":
        not_passed(f"readinessProbe must hit /readyz, found path={r_path!r}")

    if not c.get("startupProbe"):
        not_passed("no startupProbe on the web container -- required to cover the 8s slow start")

    term_ignore_present = env.get("TERM_IGNORE") == "1"
    preStop_present = bool(c.get("lifecycle", {}).get("preStop"))
    if term_ignore_present and not preStop_present:
        not_passed(
            "TERM_IGNORE=1 is still set and no lifecycle.preStop was added -- "
            "either remove TERM_IGNORE or add a preStop hook (+ terminationGracePeriodSeconds)"
        )

    rolling = spec.get("strategy", {}).get("rollingUpdate", {})
    max_unavailable = str(rolling.get("maxUnavailable", "25%"))
    if max_unavailable not in ("0", "0%"):
        not_passed(
            f"rollingUpdate.maxUnavailable must be 0 to keep full capacity during rollout, "
            f"found {max_unavailable!r}"
        )
    max_surge = rolling.get("maxSurge", 1)
    try:
        surge_ok = int(str(max_surge).rstrip("%")) >= 1
    except ValueError:
        surge_ok = False
    if not surge_ok:
        not_passed(f"rollingUpdate.maxSurge must be >= 1 (or >=100%), found {max_surge!r}")


def _wait_initial_rollout():
    wait_rollout("deployment/web", NS, timeout=INITIAL_ROLLOUT_TIMEOUT_S)


def _start_loadgen():
    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "loadgen"},
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "loadgen",
                    "image": "sandbox20-app:1.0",
                    "imagePullPolicy": "Never",
                    "command": ["python3", "-c", LOAD_SCRIPT],
                }
            ],
        },
    }
    kubectl("apply", "-f", "-", ns=NS, input=json.dumps(pod_manifest))


def _pod_phase(name: str) -> str:
    data = kubectl_json("get", "pod", name, ns=NS, check=False)
    return data.get("status", {}).get("phase", "")


def _trigger_rollout_to_v2():
    kubectl("set", "image", "deployment/web", "web=sandbox20-app:2.0", ns=NS)
    wait_rollout("deployment/web", NS, timeout=ROLLING_UPDATE_TIMEOUT_S)


def _wait_loadgen_done():
    wait_until(
        lambda: _pod_phase("loadgen") in ("Succeeded", "Failed"),
        timeout=LOADGEN_WAIT_TIMEOUT_S,
        interval=3.0,
        desc="load generator pod to finish",
    )
    phase = _pod_phase("loadgen")
    if phase != "Succeeded":
        logs = kubectl("logs", "pod/loadgen", ns=NS, check=False).stdout
        not_passed(f"load generator pod ended in phase={phase}, not Succeeded; logs tail: {logs[-500:]}")


def _parse_loadgen_result() -> tuple[int, int]:
    logs = kubectl("logs", "pod/loadgen", ns=NS).stdout
    m = re.search(r"RESULT ok=(\d+) fail=(\d+)", logs)
    if not m:
        not_passed(f"could not find a RESULT line in load generator logs: {logs[-500:]}")
    return int(m.group(1)), int(m.group(2))


def _check_final_pods():
    pods = kubectl_json("get", "pods", "-l", "app=web", ns=NS).get("items", [])
    if not pods:
        not_passed("no web pods found after the rollout")

    bad_image = []
    total_restarts = 0
    for p in pods:
        statuses = p.get("status", {}).get("containerStatuses", [])
        for cs in statuses:
            image = cs.get("image", "")
            if not image.endswith("sandbox20-app:2.0"):
                bad_image.append((p["metadata"]["name"], image))
            total_restarts += cs.get("restartCount", 0)

    if bad_image:
        not_passed(f"pod(s) not running sandbox20-app:2.0 after rollout: {bad_image}")
    if total_restarts != 0:
        not_passed(f"container restarts != 0 after the rollout (total={total_restarts}) -- probes killed a pod")


@guarded
def main():
    require_cluster()

    try:
        delete_ns(NS, wait=True)
        ensure_ns(NS)

        _apply_given_and_learner()
        _wait_initial_rollout()

        dep = _get_live_deployment()
        _check_anti_cheat(dep)

        _start_loadgen()
        time.sleep(5)  # let the load generator establish a steady-state baseline at v1 first

        _trigger_rollout_to_v2()

        _wait_loadgen_done()
        ok, fail = _parse_loadgen_result()

        if fail != 0:
            not_passed(f"load generator saw {fail} failed request(s) during the rollout (ok={ok}) -- not zero-downtime")
        if ok < LOAD_MIN_OK:
            not_passed(f"load generator only completed {ok} successful requests (< {LOAD_MIN_OK}) -- test looks vacuous")

        _check_final_pods()

        passed(f"zero-downtime rollout to 2.0 confirmed: {ok} requests, 0 failures, 0 container restarts")
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
