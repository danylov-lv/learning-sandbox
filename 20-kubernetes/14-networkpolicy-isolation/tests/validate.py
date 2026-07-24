"""Validator for 20-kubernetes task 14 (networkpolicy-isolation).

Run from this task directory:

    uv run python tests/validate.py

Seeds the topology (queue, target, worker, decoy in namespace t14; outsider
in namespace t14-external), waits for every Deployment to roll out, applies
the learner's src/networkpolicy.yaml (a no-op if it's still the unfilled
TODO stub -- kubectl reports "no objects passed to apply" and the validator
treats that the same as "no policy applied yet"), then runs six one-shot
probe Jobs and asserts:

  - worker -> queue:6379   MUST succeed (its queue)
  - worker -> target:8080  MUST succeed (its allowed scrape target)
  - worker -> decoy:8080   MUST be BLOCKED (same-namespace neighbor, not on
    the allow-list)
  - worker -> outsider:8080 (namespace t14-external) MUST be BLOCKED
    (cross-namespace neighbor, not on the allow-list)
  - decoy -> worker:8080   MUST be BLOCKED (nothing may reach worker)
  - outsider -> worker:8080 (from t14-external) MUST be BLOCKED

Each probe Job runs sandbox20-app:1.0 with its entrypoint overridden to a
short python3 socket.create_connection() one-liner, carrying the labels of
whichever component it's impersonating (app=worker, app=decoy, etc.) so the
learner's NetworkPolicy -- which selects by those exact labels -- actually
applies to it. A "should succeed but was blocked" or "should be blocked but
succeeded" mismatch anywhere is a single NOT PASSED line naming which leg
failed and how.

With the stub in place (no policy applied), the topology is fully open, so
every one of the four negative probes above succeeds when it should have
been blocked -- the validator fails on the very first one it checks, and
the failure message says exactly that (not "stub detected"): this is a
behavioral check, not a text-content check.

Namespaces t14 and t14-external are deleted (best-effort, non-blocking)
whether this passes or fails.
"""

from __future__ import annotations

import json
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
    require_cluster,
    wait_rollout,
    wait_until,
)

NS = "t14"
NS_EXT = "t14-external"
GIVEN_DIR = TASK_ROOT / "given"
POLICY_PATH = TASK_ROOT / "src" / "networkpolicy.yaml"

PROBE_IMAGE = "sandbox20-app:1.0"
CONNECT_TIMEOUT_S = 3.0
JOB_WAIT_S = 60

PROBE_SCRIPT = (
    "import socket, sys\n"
    "host, port, timeout = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])\n"
    "try:\n"
    "    s = socket.create_connection((host, port), timeout=timeout)\n"
    "    s.close()\n"
    "    print('PROBE_RESULT=CONNECTED')\n"
    "    sys.exit(0)\n"
    "except Exception as e:\n"
    "    print(f'PROBE_RESULT=BLOCKED: {e}')\n"
    "    sys.exit(1)\n"
)


def _seed_topology():
    delete_ns(NS, wait=True)
    delete_ns(NS_EXT, wait=True)
    ensure_ns(NS)
    ensure_ns(NS_EXT)

    for fname in ("queue.yaml", "target.yaml", "decoy.yaml", "worker.yaml"):
        result = kubectl("apply", "-f", str(GIVEN_DIR / fname), ns=NS, check=False, timeout=60)
        if result.returncode != 0:
            not_passed(f"kubectl apply -f given/{fname} failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")

    result = kubectl("apply", "-f", str(GIVEN_DIR / "outsider.yaml"), ns=NS_EXT, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f given/outsider.yaml failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")

    for name in ("queue", "target", "decoy", "worker"):
        wait_rollout(f"deployment/{name}", NS, timeout=120)
    wait_rollout("deployment/outsider", NS_EXT, timeout=120)


def _apply_policy():
    if not POLICY_PATH.exists():
        not_passed(f"missing {POLICY_PATH}")
    text = POLICY_PATH.read_text(encoding="utf-8")
    if not text.strip():
        return  # empty stub -- no policy applied, later probes will show the open topology

    result = kubectl("apply", "-n", NS, "-f", str(POLICY_PATH), check=False, timeout=30)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "no objects passed to apply" in stderr:
            # A pure-comment TODO stub applies to nothing -- treat the same
            # as "no policy yet". The probes below are what actually explain
            # the failure to the learner, not this line.
            return
        not_passed(
            "kubectl apply -n t14 -f src/networkpolicy.yaml failed: "
            f"{stderr.splitlines()[-1] if stderr else result.stdout.strip()}"
        )


def _job_manifest(name: str, labels: dict, host: str, port: int) -> dict:
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 60,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "probe",
                            "image": PROBE_IMAGE,
                            "imagePullPolicy": "IfNotPresent",
                            "command": [
                                "python3",
                                "-c",
                                PROBE_SCRIPT,
                                host,
                                str(port),
                                str(CONNECT_TIMEOUT_S),
                            ],
                        }
                    ],
                },
            },
        },
    }


def _run_probe(name: str, ns: str, labels: dict, host: str, port: int) -> tuple[bool, str]:
    kubectl("delete", "job", name, "--ignore-not-found=true", "--wait=true", ns=ns, check=False, timeout=30)
    manifest = _job_manifest(name, labels, host, port)
    kubectl("apply", "-f", "-", ns=ns, input=json.dumps(manifest), timeout=30)

    def _terminal() -> bool:
        job = kubectl_json("get", "job", name, ns=ns, check=False)
        st = job.get("status", {})
        return st.get("succeeded", 0) >= 1 or st.get("failed", 0) >= 1

    wait_until(_terminal, timeout=JOB_WAIT_S, interval=1.5, desc=f"probe job/{name} to finish")

    job = kubectl_json("get", "job", name, ns=ns, check=False)
    succeeded = job.get("status", {}).get("succeeded", 0) >= 1
    logs = kubectl("logs", f"job/{name}", ns=ns, check=False, timeout=20).stdout
    kubectl("delete", "job", name, "--ignore-not-found=true", "--wait=false", ns=ns, check=False, timeout=15)
    return succeeded, logs


def _last_useful_line(logs: str) -> str:
    for line in reversed((logs or "").splitlines()):
        if line.strip():
            return line.strip()
    return "(no probe output -- pod may not have started in time)"


def _expect_allowed(job_name: str, ns: str, labels: dict, host: str, port: int, description: str):
    ok, logs = _run_probe(job_name, ns, labels, host, port)
    if not ok:
        not_passed(
            f"{description}: expected to REACH {host}:{port} but it was blocked "
            f"({_last_useful_line(logs)}) -- your NetworkPolicy denies traffic it should allow"
        )


def _expect_blocked(job_name: str, ns: str, labels: dict, host: str, port: int, description: str):
    ok, logs = _run_probe(job_name, ns, labels, host, port)
    if ok:
        not_passed(
            f"{description}: expected {host}:{port} to be BLOCKED but the connection succeeded "
            f"({_last_useful_line(logs)}) -- your NetworkPolicy is missing or not restrictive enough"
        )


@guarded
def main():
    require_cluster()
    try:
        _seed_topology()
        _apply_policy()

        # Probes go through each component's Service (name, Service port 80),
        # exactly like real traffic would -- kube-proxy DNATs that to the
        # pod's actual containerPort 8080 before Calico ever evaluates the
        # learner's policy. queue has no such split (Service port ==
        # container port == 6379).
        _expect_allowed("probe-worker-to-queue", NS, {"app": "worker"}, "queue", 6379, "worker -> queue")
        _expect_allowed("probe-worker-to-target", NS, {"app": "worker"}, "target", 80, "worker -> target")

        _expect_blocked("probe-worker-to-decoy", NS, {"app": "worker"}, "decoy", 80, "worker -> decoy")
        _expect_blocked(
            "probe-worker-to-outsider", NS, {"app": "worker"},
            f"outsider.{NS_EXT}.svc.cluster.local", 80, "worker -> outsider (cross-namespace)",
        )
        _expect_blocked("probe-decoy-to-worker", NS, {"app": "decoy"}, "worker", 80, "decoy -> worker")
        _expect_blocked(
            "probe-outsider-to-worker", NS_EXT, {"app": "outsider"},
            f"worker.{NS}.svc.cluster.local", 80, "outsider -> worker (cross-namespace)",
        )

        passed(
            "worker reaches queue+target, worker cannot reach decoy/outsider, "
            "nothing can reach worker"
        )
    finally:
        delete_ns(NS, wait=False)
        delete_ns(NS_EXT, wait=False)


if __name__ == "__main__":
    main()
