"""Validator for 20-kubernetes task 20 (pdb-vs-node-drains).

Run from this task directory:

    uv run python tests/validate.py

Seeds a 4-replica `web` Deployment (soft-spread across the two worker nodes)
into t20, applies the learner's PodDisruptionBudget, then drains the web pods
off one worker with `kubectl drain --pod-selector app=web` while continuously
polling that the Deployment's Ready replicas never drop below the PDB's
desiredHealthy. Asserts the PDB actually selects the web pods and is neither
too weak nor too strict, that the drain completes, that the drained node no
longer hosts web pods, and that the fleet returns to 4 Ready.

This is the ONLY task in the module allowed to cordon/drain nodes. EVERY node
is uncordoned and namespace t20 deleted at the end -- whether this passes or
fails -- via a finally block (harness `guarded` re-raises SystemExit, so the
finally still runs on failure).
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness import common

NS = "t20"
DEP = "web"
REPLICAS = 4
DEPLOY_PATH = TASK_ROOT / "given" / "deployment.yaml"
PDB_PATH = TASK_ROOT / "src" / "pdb.yaml"


def _all_nodes() -> list[str]:
    data = common.kubectl_json("get", "nodes")
    return [n["metadata"]["name"] for n in data.get("items", [])]


def _uncordon_all() -> None:
    for node in _all_nodes():
        common.kubectl("uncordon", node, check=False, timeout=30)


def _web_pods_by_node() -> dict:
    data = common.kubectl_json("get", "pods", "-l", f"app={DEP}", ns=NS)
    out: dict = {}
    for p in data.get("items", []):
        node = p.get("spec", {}).get("nodeName")
        out.setdefault(node, []).append(p["metadata"]["name"])
    return out


def _ready_replicas() -> int:
    data = common.kubectl_json("get", "deployment", DEP, ns=NS)
    return data.get("status", {}).get("readyReplicas", 0) or 0


@common.guarded
def main() -> None:
    common.require_cluster()
    try:
        # A prior run's finally deletes t20 asynchronously; make sure any
        # lingering termination has finished before recreating it.
        common.delete_ns(NS, wait=True)
        common.ensure_ns(NS)
        common.kubectl("apply", "-f", str(DEPLOY_PATH), ns=NS)
        common.wait_rollout(f"deployment/{DEP}", NS, timeout=150)

        by_node = _web_pods_by_node()
        worker_nodes = [n for n in by_node if n and "worker" in n]
        if len(worker_nodes) < 2:
            common.not_passed(
                f"fixture is not spread across both workers (web pods on "
                f"{sorted(n for n in by_node if n)}) -- cannot exercise a drain"
            )

        res = common.kubectl("apply", "-f", str(PDB_PATH), ns=NS, check=False)
        if res.returncode != 0:
            common.not_passed(f"kubectl apply -f src/pdb.yaml failed: {common._last_line(res.stderr)}")

        pdbs = common.kubectl_json("get", "pdb", ns=NS).get("items", [])
        if not pdbs:
            common.not_passed("no PodDisruptionBudget found in t20 after applying src/pdb.yaml")
        pdb_name = pdbs[0]["metadata"]["name"]

        def _pdb_observed() -> bool:
            d = common.kubectl_json("get", "pdb", pdb_name, ns=NS)
            return (d.get("status", {}).get("expectedPods", 0) or 0) >= REPLICAS

        common.wait_until(_pdb_observed, timeout=40, desc="the PDB to observe the web pods")

        pstat = common.kubectl_json("get", "pdb", pdb_name, ns=NS).get("status", {})
        expected = pstat.get("expectedPods", 0) or 0
        desired = pstat.get("desiredHealthy", 0) or 0
        current = pstat.get("currentHealthy", 0) or 0
        if expected < REPLICAS or current < REPLICAS:
            common.not_passed(
                f"your PDB does not select the web pods (expectedPods={expected}, "
                f"currentHealthy={current}, want {REPLICAS}) -- check the selector"
            )
        if desired < REPLICAS - 1:
            common.not_passed(
                f"your PDB is too weak: desiredHealthy={desired}, need at least "
                f"{REPLICAS - 1} (keep >=3 of 4 available; use minAvailable: 3 or maxUnavailable: 1)"
            )
        if desired >= REPLICAS:
            common.not_passed(
                f"your PDB is too strict: desiredHealthy={desired} == replicas, which forbids "
                "ALL voluntary eviction and would block the drain forever -- leave one disruption of headroom"
            )

        by_node = _web_pods_by_node()
        target = next((n for n, pods in by_node.items() if n and "worker" in n and pods), None)
        if target is None:
            common.not_passed("could not find a worker node hosting web pods to drain")

        min_ready = {"v": REPLICAS}
        stop = threading.Event()

        def _poll() -> None:
            while not stop.is_set():
                try:
                    r = _ready_replicas()
                    if r < min_ready["v"]:
                        min_ready["v"] = r
                except Exception:
                    pass
                time.sleep(1)

        poller = threading.Thread(target=_poll, daemon=True)
        poller.start()
        drain = common.kubectl(
            "drain", target, "--pod-selector", f"app={DEP}",
            "--ignore-daemonsets", "--delete-emptydir-data", "--timeout=180s",
            check=False, timeout=210,
        )
        stop.set()
        poller.join(timeout=5)

        if drain.returncode != 0:
            common.not_passed(
                f"kubectl drain {target} (web pods only) did not complete -- your PDB may forbid "
                f"enough disruption to make progress: {common._last_line(drain.stderr or drain.stdout)}"
            )
        if min_ready["v"] < desired:
            common.not_passed(
                f"availability dropped below the budget during the drain: minimum Ready web "
                f"replicas observed was {min_ready['v']}, PDB desiredHealthy={desired}"
            )

        common.wait_until(
            lambda: target not in _web_pods_by_node(), timeout=90,
            desc=f"web pods to be evicted off the drained node {target}",
        )
        common.wait_until(
            lambda: _ready_replicas() >= REPLICAS, timeout=150,
            desc="the web Deployment to return to 4 Ready",
        )
        common.passed(
            f"PDB held web >= {desired}/{REPLICAS} Ready through a drain of {target} "
            f"(minimum observed {min_ready['v']}); fleet recovered to {REPLICAS}"
        )
    finally:
        _uncordon_all()
        common.delete_ns(NS)


if __name__ == "__main__":
    main()
