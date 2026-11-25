"""CP1 validator for task 11 (Arc 3 capstone) -- health restoration, the
fix-path-agnostic hard gate.

Run from this task directory:

    uv run python tests/validate_cp1.py

What it does, in order:

  1. Seeds the incident fresh into namespace t11 (equivalent of
     given/setup.sh, done directly): redis, the broken pipeline-config
     ConfigMap (QUEUE_KEE instead of QUEUE_KEY), api, worker, producer.
  2. Confirms the seeded state is actually broken the way the task claims
     -- a non-vacuous check, same spirit as task 09's fixture self-check:
     api and worker must show CrashLoopBackOff, and the redis queue must
     visibly be growing with nobody consuming it. If this step fails, the
     fixture itself is broken, not the learner's fix.
  3. Applies src/pipeline-config-fix.yaml on top, then rollout-restarts
     api/worker/producer so each picks up the corrected ConfigMap at a
     fresh container start (a plain ConfigMap edit does not retroactively
     change an already-running container's resolved environment -- this
     restart step is a normal ops action after any ConfigMap fix, not
     something specific to one fix strategy).
  4. Asserts the healthy target state: every Deployment in t11 available
     at full desired replicas, no pod anywhere in t11 in CrashLoopBackOff,
     /readyz green through Service api, and the pipeline actually flowing
     (worker's own app_processed_total rising over a real window).
  5. Durability check: scales api and worker to 0 and back up to their
     original replica counts (a full fresh pod, not a crash-loop restart
     reusing timing) and re-confirms the same healthy target state --
     proving the fix lives in the ConfigMap/Deployment objects themselves,
     not in one lucky pod instance.

This is deliberately indifferent to HOW the learner fixed
pipeline-config.yaml's content, as long as the end state above holds.

Namespace t11 is deleted (best-effort, non-blocking) whether this passes
or fails.
"""

from __future__ import annotations

import re
import sys
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
    port_forward,
    http_get,
    require_cluster,
    wait_rollout,
    wait_until,
)

NS = "t11"
GIVEN_DIR = TASK_ROOT / "given"
SRC_FIX = TASK_ROOT / "src" / "pipeline-config-fix.yaml"

DEPLOYMENTS = ["redis", "api", "worker", "producer"]
RESTART_ON_FIX = ["api", "worker", "producer"]
CRASH_APPS_EXPECTED_BROKEN = ["api", "worker"]

QUEUE_KEY_BROKEN = "sandbox20:queue"  # app.py's built-in default, used when
# QUEUE_KEY never resolves from the (typo'd) ConfigMap -- this is what
# producer actually pushes into while the incident is live.

SEED_TIMEOUT_S = 90
FIX_ROLLOUT_TIMEOUT_S = 120
HEALTH_TIMEOUT_S = 90
DRAIN_SAMPLE_GAP_S = 8
DURABILITY_ROLLOUT_TIMEOUT_S = 90


def _seed_fixture():
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    for name in ("redis.yaml", "pipeline-config.yaml", "api.yaml", "worker.yaml", "producer.yaml"):
        result = kubectl("apply", "-f", str(GIVEN_DIR / name), ns=NS, check=False, timeout=60)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()
            not_passed(f"kubectl apply -f given/{name} failed: {tail[-1] if tail else '(no output)'}")


def _pod_items(ns=NS):
    return kubectl_json("get", "pods", ns=ns).get("items", [])


def _pods_for_app(app, ns=NS):
    return kubectl_json("get", "pods", "-l", f"app={app}", ns=ns).get("items", [])


def _container_waiting_reasons(pod):
    reasons = []
    for cs in pod.get("status", {}).get("containerStatuses", []):
        waiting = cs.get("state", {}).get("waiting")
        if waiting:
            reasons.append(waiting.get("reason", ""))
    return reasons


def _any_crashlooping(app):
    for pod in _pods_for_app(app):
        if "CrashLoopBackOff" in _container_waiting_reasons(pod):
            return True
    return False


def _redis_llen(key):
    result = kubectl("exec", "deploy/redis", "--", "redis-cli", "llen", key, ns=NS, check=False, timeout=30)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _verify_broken_non_vacuous():
    def _both_crashlooping():
        return all(_any_crashlooping(app) for app in CRASH_APPS_EXPECTED_BROKEN)

    wait_until(
        _both_crashlooping,
        timeout=SEED_TIMEOUT_S,
        interval=3,
        desc="api and worker to show CrashLoopBackOff on the freshly seeded (broken) fixture",
    )

    first = _redis_llen(QUEUE_KEY_BROKEN)
    if first is None:
        not_passed("could not read queue depth via redis-cli llen against the freshly seeded fixture")

    def _queue_growing():
        current = _redis_llen(QUEUE_KEY_BROKEN)
        return current is not None and current > first

    wait_until(
        _queue_growing,
        timeout=30,
        interval=3,
        desc=f"redis key {QUEUE_KEY_BROKEN!r} to grow (producer pushing, nothing consuming) on the broken fixture",
    )


def _apply_fix_and_restart():
    if not SRC_FIX.exists():
        not_passed(f"missing {SRC_FIX}")
    result = kubectl("apply", "-f", str(SRC_FIX), ns=NS, check=False, timeout=30)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()
        not_passed(f"kubectl apply -f src/pipeline-config-fix.yaml failed: {tail[-1] if tail else '(no output)'}")

    for name in RESTART_ON_FIX:
        kubectl("rollout", "restart", f"deployment/{name}", ns=NS, timeout=30)
    for name in RESTART_ON_FIX:
        wait_rollout(f"deployment/{name}", NS, timeout=FIX_ROLLOUT_TIMEOUT_S)


def _deployments_available():
    for name in DEPLOYMENTS:
        dep = kubectl_json("get", "deployment", name, ns=NS, check=False)
        if not dep:
            return False
        spec_replicas = dep.get("spec", {}).get("replicas", 1)
        available = dep.get("status", {}).get("availableReplicas", 0)
        if available != spec_replicas:
            return False
    return True


def _no_crashloop():
    for pod in _pod_items():
        if "CrashLoopBackOff" in _container_waiting_reasons(pod):
            return False
    return True


def _readyz_green_through_service():
    with port_forward("svc/api", 80, NS) as local_port:
        status, _body = http_get(f"http://127.0.0.1:{local_port}/readyz", timeout=5)
        return status == 200


def _processed_total(local_port):
    status, body = http_get(f"http://127.0.0.1:{local_port}/metrics", timeout=5)
    if status != 200:
        return None
    m = re.search(r"^app_processed_total (\d+)$", body, re.MULTILINE)
    return int(m.group(1)) if m else None


def _queue_actually_draining():
    with port_forward("svc/worker", 80, NS) as local_port:
        first = _processed_total(local_port)
        if first is None:
            not_passed("worker /metrics did not report app_processed_total")

        def _advanced():
            current = _processed_total(local_port)
            return current is not None and current > first

        wait_until(
            _advanced,
            timeout=DRAIN_SAMPLE_GAP_S + 20,
            interval=2,
            desc="worker app_processed_total to advance (queue actually draining end to end)",
        )


def _assert_healthy_target(label):
    wait_until(
        lambda: _deployments_available() and _no_crashloop(),
        timeout=HEALTH_TIMEOUT_S,
        interval=3,
        desc=f"all Deployments available with no CrashLoopBackOff ({label})",
    )
    if not _readyz_green_through_service():
        not_passed(f"/readyz through Service api is not 200 ({label})")
    _queue_actually_draining()


def _scale(name, replicas):
    kubectl("scale", f"deployment/{name}", f"--replicas={replicas}", ns=NS, timeout=30)


def _original_replicas(name):
    dep = kubectl_json("get", "deployment", name, ns=NS)
    return dep.get("spec", {}).get("replicas", 1)


def _check_durability():
    originals = {name: _original_replicas(name) for name in ("api", "worker")}

    for name in ("api", "worker"):
        _scale(name, 0)
    wait_until(
        lambda: not _pods_for_app("api") and not _pods_for_app("worker"),
        timeout=60,
        interval=2,
        desc="api and worker pods to fully terminate after scale-to-zero",
    )

    for name in ("api", "worker"):
        _scale(name, originals[name])
    for name in ("api", "worker"):
        wait_rollout(f"deployment/{name}", NS, timeout=DURABILITY_ROLLOUT_TIMEOUT_S)

    _assert_healthy_target("after scale-to-zero-and-back durability check")


@guarded
def main():
    require_cluster()
    try:
        _seed_fixture()
        _verify_broken_non_vacuous()
        _apply_fix_and_restart()
        _assert_healthy_target("immediately after the fix")
        _check_durability()
        passed(
            "pipeline restored: all Deployments available, no CrashLoopBackOff, "
            "/readyz green through Service api, queue draining end to end, "
            "fix survives a full scale-to-zero-and-back"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
