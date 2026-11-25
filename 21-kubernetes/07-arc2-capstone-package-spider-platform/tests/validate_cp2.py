"""CP2 validator for task 07 (Arc 2 capstone) -- LIVE BEHAVIOR.

Requires the live `sandbox20` cluster. Installs the chart into namespace
`t07` (release `t07-spider`) with `values-dev.yaml`, waits for every
rollout, then:

  1. Port-forwards to ONE `workers` pod and watches `/metrics` over a
     ~30s window: `app_processed_total` must rise by a real amount (the
     pipeline is actually flowing, not just "pods are Running"), while
     `app_queue_depth` stays bounded throughout (values-dev.yaml's
     producer rate is supposed to sit comfortably under one worker's
     drain capacity).
  2. `helm upgrade`s the same release to `values-prod.yaml`. Checks: all 3
     workers reach `readyReplicas == 3`; queue depth stays bounded under
     the new (faster) producer and (larger) worker pool; and the `queue`
     pod's own `status.startTime` is UNCHANGED across the upgrade -- proof
     the chart's queue template didn't change between values files and
     selectors are stable (an upgrade that recreated the queue pod would
     have dropped whatever was in the queue).

No wall-clock performance gate: the processed/queue-depth thresholds below
are generous structural bounds (see README.md's rate contract), not tuned
to one machine -- PROCESS_MS/RATE_PER_S are simulated, not CPU-bound, so
throughput is deterministic regardless of machine speed.

Cleans up its own install (helm uninstall + delete namespace) whether it
passes or fails -- safe to re-run.

Run from this task directory (needs the cluster up -- see
`../scripts/cluster-up.sh` / `../scripts/build-images.sh` from the module
root if it isn't):

    uv run python tests/validate_cp2.py
"""

import subprocess
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    CONTEXT,
    delete_ns,
    ensure_ns,
    guarded,
    http_get,
    kubectl_json,
    not_passed,
    passed,
    port_forward,
    require_cluster,
    wait_rollout,
    wait_until,
)

CHART_DIR = TASK_ROOT / "chart"
NS = "t07"
RELEASE = "t07-spider"
COMPONENTS = ("target", "queue", "producer", "workers")

WINDOW_S = 30
POLL_INTERVAL_S = 5
MIN_PROCESSED_DELTA = 15   # generous floor; dev capacity/rate contract expects far more
MAX_QUEUE_DEPTH_DEV = 60
MAX_QUEUE_DEPTH_PROD = 150


def _tail(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def helm(*args, timeout=180):
    cmd = ["helm", "--kube-context", CONTEXT] + list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(TASK_ROOT))
    except FileNotFoundError:
        not_passed("helm not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"helm {' '.join(args)} timed out after {timeout}s")


def cleanup():
    helm("uninstall", RELEASE, "-n", NS, timeout=60)
    delete_ns(NS, wait=True)


def deployments_for(component):
    data = kubectl_json("get", "deployments", "-l", f"app.kubernetes.io/component={component}", ns=NS)
    return [item["metadata"]["name"] for item in data.get("items", [])]


def pods_for(component):
    data = kubectl_json("get", "pods", "-l", f"app.kubernetes.io/component={component}", ns=NS)
    return data.get("items", [])


def wait_all_rollouts():
    for component in COMPONENTS:
        for dep in deployments_for(component):
            wait_rollout(f"deployment/{dep}", NS, timeout=150)


def parse_metrics(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        name, raw = parts
        try:
            values[name] = float(raw)
        except ValueError:
            pass
    return values


def fetch_metrics(local_port):
    status, body = http_get(f"http://127.0.0.1:{local_port}/metrics")
    if status != 200:
        not_passed(f"GET /metrics returned {status!r}: {body}")
    return parse_metrics(body)


def sample_worker_over_window(pod_name, window_s, poll_interval_s):
    """Returns (processed_start, processed_end, [queue_depth samples])."""
    with port_forward(f"pod/{pod_name}", 8080, NS) as local_port:
        m0 = fetch_metrics(local_port)
        processed_start = m0.get("app_processed_total")
        if processed_start is None:
            not_passed("worker /metrics has no app_processed_total -- check WORK_MODE=consumer wiring")

        depths = []
        d0 = m0.get("app_queue_depth", -1)
        if d0 >= 0:
            depths.append(d0)

        deadline = time.monotonic() + window_s
        last = m0
        while time.monotonic() < deadline:
            time.sleep(poll_interval_s)
            last = fetch_metrics(local_port)
            d = last.get("app_queue_depth", -1)
            if d >= 0:
                depths.append(d)

        processed_end = last.get("app_processed_total", processed_start)
    return processed_start, processed_end, depths


@guarded
def main():
    require_cluster()
    cleanup()  # defensive: clear any leftover install from a previous interrupted run

    try:
        ensure_ns(NS)

        install = helm("install", RELEASE, str(CHART_DIR), "-n", NS, "-f", str(CHART_DIR / "values-dev.yaml"))
        if install.returncode != 0:
            not_passed(f"helm install failed: {_tail(install.stdout + install.stderr)}")

        wait_all_rollouts()

        worker_pods = pods_for("workers")
        if not worker_pods:
            not_passed("no pod found with app.kubernetes.io/component=workers after install")

        processed_start, processed_end, depths_dev = sample_worker_over_window(
            worker_pods[0]["metadata"]["name"], WINDOW_S, POLL_INTERVAL_S
        )
        processed_delta = processed_end - processed_start
        if processed_delta < MIN_PROCESSED_DELTA:
            not_passed(
                f"app_processed_total rose by only {processed_delta:.0f} over ~{WINDOW_S}s "
                f"(from {processed_start:.0f} to {processed_end:.0f}) -- pipeline does not look like it's flowing"
            )
        if not depths_dev:
            not_passed("never observed a valid app_queue_depth reading during the dev-values window")
        max_depth_dev = max(depths_dev)
        if max_depth_dev > MAX_QUEUE_DEPTH_DEV:
            not_passed(
                f"app_queue_depth reached {max_depth_dev:.0f} during the dev-values window (bound "
                f"{MAX_QUEUE_DEPTH_DEV}) -- values-dev.yaml's producer.ratePerS is not comfortably under "
                "worker drain capacity"
            )

        queue_pods_before = pods_for("queue")
        if len(queue_pods_before) != 1:
            not_passed(f"expected exactly one queue pod before upgrade, found {len(queue_pods_before)}")
        queue_name_before = queue_pods_before[0]["metadata"]["name"]
        queue_start_before = queue_pods_before[0].get("status", {}).get("startTime")

        upgrade = helm("upgrade", RELEASE, str(CHART_DIR), "-n", NS, "-f", str(CHART_DIR / "values-prod.yaml"))
        if upgrade.returncode != 0:
            not_passed(f"helm upgrade failed: {_tail(upgrade.stdout + upgrade.stderr)}")

        wait_all_rollouts()

        def three_workers_ready():
            deps = deployments_for("workers")
            if len(deps) != 1:
                return False
            data = kubectl_json("get", "deployment", deps[0], ns=NS)
            return data.get("status", {}).get("readyReplicas") == 3

        wait_until(three_workers_ready, timeout=150, desc="3 ready workers after the prod upgrade")

        queue_pods_after = pods_for("queue")
        if len(queue_pods_after) != 1:
            not_passed(f"expected exactly one queue pod after upgrade, found {len(queue_pods_after)}")
        queue_name_after = queue_pods_after[0]["metadata"]["name"]
        queue_start_after = queue_pods_after[0].get("status", {}).get("startTime")

        if queue_name_after != queue_name_before:
            not_passed(
                f"queue pod was recreated by the dev->prod upgrade ({queue_name_before} -> {queue_name_after}) "
                "-- the queue template must not change between values-dev.yaml and values-prod.yaml, and "
                "selectors must stay stable"
            )
        if queue_start_after != queue_start_before:
            not_passed(
                f"queue pod's startTime changed across the upgrade ({queue_start_before} -> {queue_start_after}) "
                "-- it was restarted, which would have dropped whatever was in the queue"
            )

        worker_pods_after = pods_for("workers")
        if not worker_pods_after:
            not_passed("no worker pods found after the prod upgrade")
        _, _, depths_prod = sample_worker_over_window(worker_pods_after[0]["metadata"]["name"], 15, POLL_INTERVAL_S)
        if depths_prod and max(depths_prod) > MAX_QUEUE_DEPTH_PROD:
            not_passed(
                f"app_queue_depth reached {max(depths_prod):.0f} after the prod upgrade (bound "
                f"{MAX_QUEUE_DEPTH_PROD}) -- values-prod.yaml's producer.ratePerS is not comfortably under "
                "the new worker capacity"
            )

        passed(
            f"pipeline flowing (processed +{processed_delta:.0f} over ~{WINDOW_S}s, max depth "
            f"{max_depth_dev:.0f} in dev); prod upgrade: 3/3 workers ready, queue pod untouched "
            f"(startTime unchanged at {queue_start_after})"
        )
    finally:
        cleanup()


if __name__ == "__main__":
    main()
