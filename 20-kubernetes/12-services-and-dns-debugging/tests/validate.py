"""Validator for 20-kubernetes task 12 (services-and-dns-debugging).

Run from this task directory:

    uv run python tests/validate.py

Recreates namespace t12, applies given/broken.yaml (a healthy
catalog-backend Deployment plus three broken Services: catalog with a
selector mismatch, catalog-batch with a wrong targetPort, catalog-peer
wrongly headless), and first confirms each broken symptom is actually
reproduced (non-vacuous check) before giving any credit. Runs a probe Job
inside t12 that resolves each Service's DNS name and curls it on its
documented port (80) -- expects it to fail against the seeded state.
Applies src/catalog-fix.yaml, src/catalog-batch-fix.yaml and
src/catalog-peer-fix.yaml on top (deleting the old Service objects first,
since spec.clusterIP is immutable and catalog-peer's fix needs to flip it),
checks the specific fields each fix was supposed to touch, then reruns the
same probe Job and asserts all three targets now return 200.

Namespace t12 is deleted (best-effort, non-blocking) whether this passes or
fails.
"""

from __future__ import annotations

import sys
import textwrap
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

NS = "t12"
GIVEN_DIR = TASK_ROOT / "given"
SRC_DIR = TASK_ROOT / "src"
CATALOG_FIX = SRC_DIR / "catalog-fix.yaml"
BATCH_FIX = SRC_DIR / "catalog-batch-fix.yaml"
PEER_FIX = SRC_DIR / "catalog-peer-fix.yaml"

STUB_MARKERS = ("TODO(you)",)

PROBE_SCRIPT = """\
import socket, time, sys
import urllib.request

TARGETS = [
    ("catalog", "catalog.t12.svc.cluster.local", 80),
    ("catalog-batch", "catalog-batch.t12.svc.cluster.local", 80),
    ("catalog-peer", "catalog-peer.t12.svc.cluster.local", 80),
]

ok = True
for label, host, port in TARGETS:
    resolved = None
    for _ in range(15):
        try:
            resolved = socket.gethostbyname(host)
            break
        except OSError:
            time.sleep(1)
    if resolved is None:
        print(f"{label}: RESOLVE_FAILED")
        ok = False
        continue
    print(f"{label}: RESOLVED={resolved}")

    status = None
    for _ in range(5):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/", timeout=3) as r:
                status = r.status
            break
        except Exception as e:
            status = f"ERROR:{type(e).__name__}"
            time.sleep(1)
    print(f"{label}: STATUS={status}")
    if status != 200:
        ok = False

sys.exit(0 if ok else 1)
"""


def _check_not_stub(path: Path):
    if not path.exists():
        not_passed(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip() or any(marker in text for marker in STUB_MARKERS):
        not_passed(f"{path} still looks like the unfilled TODO stub")


def _seed_fixture():
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    result = kubectl("apply", "-f", str(GIVEN_DIR / "broken.yaml"), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f given/broken.yaml failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _endpoints_populated(name: str) -> bool:
    eps = kubectl_json("get", "endpoints", name, ns=NS, check=False)
    subsets = eps.get("subsets") or []
    return any(a for s in subsets for a in s.get("addresses", []))


def _verify_fixture_non_vacuous():
    wait_rollout("deployment/catalog-backend", NS, timeout=90)

    catalog_eps = kubectl_json("get", "endpoints", "catalog", ns=NS, check=False)
    if catalog_eps.get("subsets"):
        not_passed(
            "Service 'catalog' already has Endpoints before any fix -- the selector-mismatch "
            "fixture didn't reproduce (expected zero Endpoints)"
        )

    wait_until(
        lambda: _endpoints_populated("catalog-batch"),
        timeout=60, interval=2,
        desc="catalog-batch Endpoints to populate (selector is correct, only the port is wrong)",
    )
    batch_eps = kubectl_json("get", "endpoints", "catalog-batch", ns=NS)
    ports = {p.get("port") for s in batch_eps.get("subsets", []) for p in s.get("ports", [])}
    if ports != {9090}:
        not_passed(
            f"Service 'catalog-batch' Endpoints report port(s) {sorted(ports)}, expected exactly "
            "{9090} before any fix -- fixture didn't reproduce the wrong-targetPort symptom"
        )

    wait_until(
        lambda: _endpoints_populated("catalog-peer"),
        timeout=60, interval=2,
        desc="catalog-peer Endpoints to populate (selector/port are correct, only headless-ness is wrong)",
    )
    peer_svc = kubectl_json("get", "svc", "catalog-peer", ns=NS)
    cluster_ip = peer_svc.get("spec", {}).get("clusterIP")
    if cluster_ip != "None":
        not_passed(
            f"Service 'catalog-peer' spec.clusterIP={cluster_ip!r}, expected 'None' before any fix -- "
            "fixture didn't reproduce the headless-misuse symptom"
        )


def _job_manifest(name: str) -> str:
    indented = textwrap.indent(PROBE_SCRIPT, " " * 14)
    return f"""\
apiVersion: batch/v1
kind: Job
metadata:
  name: {name}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 120
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: probe
          image: sandbox20-app:1.0
          imagePullPolicy: IfNotPresent
          command: ["python3", "-c"]
          args:
            - |
{indented}
"""


def _run_probe(name: str) -> tuple[bool, str]:
    kubectl("delete", "job", name, "--ignore-not-found=true", ns=NS, check=False, timeout=30)
    manifest = _job_manifest(name)
    result = kubectl("apply", "-f", "-", ns=NS, input=manifest, check=False, timeout=30)
    if result.returncode != 0:
        not_passed(f"kubectl apply of probe Job '{name}' failed: {result.stderr.strip() or result.stdout.strip()}")

    def _terminal() -> bool:
        job = kubectl_json("get", "job", name, ns=NS, check=False)
        conditions = job.get("status", {}).get("conditions", [])
        return any(c.get("type") in ("Complete", "Failed") and c.get("status") == "True" for c in conditions)

    wait_until(_terminal, timeout=150, interval=2, desc=f"probe Job '{name}' to reach a terminal state")

    logs = kubectl("logs", f"job/{name}", ns=NS, check=False, timeout=30).stdout
    job = kubectl_json("get", "job", name, ns=NS, check=False)
    succeeded = job.get("status", {}).get("succeeded", 0) >= 1
    return succeeded, logs


def _apply_fixes():
    # catalog-peer's fix needs spec.clusterIP to flip from None to a real
    # allocated IP, which is immutable on an existing Service -- delete all
    # three before re-applying so every fix lands on a clean object.
    kubectl(
        "delete", "svc", "catalog", "catalog-batch", "catalog-peer",
        "--ignore-not-found=true", ns=NS, check=False, timeout=30,
    )
    for path in (CATALOG_FIX, BATCH_FIX, PEER_FIX):
        result = kubectl("apply", "-f", str(path), ns=NS, check=False, timeout=60)
        if result.returncode != 0:
            not_passed(f"kubectl apply -f {path.name} failed: {result.stderr.strip() or result.stdout.strip()}")


def _check_fixed_structurally():
    if not kubectl_json("get", "svc", "catalog", ns=NS, check=False):
        not_passed("Service 'catalog' not found after applying src/catalog-fix.yaml")
    wait_until(
        lambda: _endpoints_populated("catalog"),
        timeout=60, interval=2,
        desc="Service 'catalog' to have Endpoints after your selector fix",
    )

    batch = kubectl_json("get", "svc", "catalog-batch", ns=NS, check=False)
    if not batch:
        not_passed("Service 'catalog-batch' not found after applying src/catalog-batch-fix.yaml")
    target_port = batch.get("spec", {}).get("ports", [{}])[0].get("targetPort")
    if str(target_port) != "8080":
        not_passed(
            f"Service 'catalog-batch' targetPort={target_port!r}, expected 8080 "
            "(catalog-backend's actual containerPort)"
        )

    peer = kubectl_json("get", "svc", "catalog-peer", ns=NS, check=False)
    if not peer:
        not_passed("Service 'catalog-peer' not found after applying src/catalog-peer-fix.yaml")
    cluster_ip = peer.get("spec", {}).get("clusterIP")
    if not cluster_ip or cluster_ip == "None":
        not_passed(
            f"Service 'catalog-peer' spec.clusterIP={cluster_ip!r}, expected a real allocated "
            "ClusterIP (not headless) after your fix"
        )


@guarded
def main():
    require_cluster()
    try:
        _check_not_stub(CATALOG_FIX)
        _check_not_stub(BATCH_FIX)
        _check_not_stub(PEER_FIX)

        _seed_fixture()
        _verify_fixture_non_vacuous()

        pre_ok, pre_logs = _run_probe("dns-probe-seed")
        if pre_ok:
            not_passed(
                "probe Job succeeded against the seeded-but-unfixed state -- the fixture isn't "
                f"actually broken the way this task expects. Probe logs:\n{pre_logs.strip()}"
            )

        _apply_fixes()
        _check_fixed_structurally()

        post_ok, post_logs = _run_probe("dns-probe")
        if not post_ok:
            not_passed(f"probe Job did not succeed after applying your fixes. Probe logs:\n{post_logs.strip()}")

        passed(
            "catalog (selector), catalog-batch (targetPort) and catalog-peer (headless) all fixed -- "
            "probe Job resolved and curled all three through their Service DNS names"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
