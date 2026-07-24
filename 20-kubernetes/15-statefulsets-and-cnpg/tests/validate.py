"""Validator for 20-kubernetes task 15 (statefulsets-and-cnpg).

Run from this task directory:

    uv run python tests/validate.py

Requires the CNPG operator already installed cluster-wide
(scripts/install.sh -- this task owns that install; it is NOT reinstalled
or uninstalled here). Applies src/cluster.yaml into namespace t15
(recreated fresh), checks the Cluster CR's own spec fields (instance
count, image, storage), waits (bounded) for the Cluster to report all
instances ready, identifies the current primary pod, force-deletes it,
and waits (bounded) for CNPG to elect a new primary and bring the cluster
back to fully-ready. Finally runs the NOTES.md doc-gate on the written
StatefulSets-vs-Deployments / failover reflection. Namespace t15 is
deleted at the end whether the task passes or fails; the CNPG operator
itself is left installed.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_keywords,
    check_sections,
    delete_ns,
    ensure_ns,
    guarded,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    require_cluster,
    wait_until,
)

NS = "t15"
SRC = TASK_ROOT / "src"
NOTES = TASK_ROOT / "NOTES.md"

OPERATOR_NS = "cnpg-system"
OPERATOR_DEPLOYMENT = "cnpg-controller-manager"
OPERATOR_CRD = "clusters.postgresql.cnpg.io"

CLUSTER_NAME = "pg-cluster"
EXPECTED_INSTANCES = 3
EXPECTED_IMAGE_PREFIX = "ghcr.io/cloudnative-pg/postgresql"

# Cluster bring-up (image pull on 3 fresh nodes + initdb + 2 replicas
# cloning via pg_basebackup) can take a few minutes on a cold cluster;
# failover (promote a replica, respawn the deleted pod, resync) is
# usually much faster but also gets a generous bound. Both are bounded
# polls, not a wall-clock performance gate.
CLUSTER_READY_TIMEOUT_S = 1200
FAILOVER_TIMEOUT_S = 900


def _require_cnpg_operator():
    dep = kubectl_json("get", "deployment", OPERATOR_DEPLOYMENT, ns=OPERATOR_NS, check=False)
    if not dep:
        not_passed(
            f"CNPG operator not installed (deployment '{OPERATOR_DEPLOYMENT}' not found in "
            f"namespace '{OPERATOR_NS}') -- run scripts/install.sh first"
        )
    ready = dep.get("status", {}).get("readyReplicas", 0)
    if not ready:
        not_passed(
            f"CNPG operator deployment '{OPERATOR_DEPLOYMENT}' has no ready replicas -- "
            "run scripts/install.sh and wait for it to finish"
        )

    crd = kubectl("get", "crd", OPERATOR_CRD, check=False, timeout=20)
    if crd.returncode != 0:
        not_passed(f"CRD '{OPERATOR_CRD}' not found -- run scripts/install.sh first")


def _apply_cluster():
    result = kubectl("apply", "-f", str(SRC / "cluster.yaml"), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"kubectl apply -f cluster.yaml failed: {err}")


def _get_cluster():
    return kubectl_json("get", "cluster.postgresql.cnpg.io", CLUSTER_NAME, ns=NS, check=False)


def _check_cluster_spec():
    cluster = _get_cluster()
    if not cluster:
        not_passed(
            f"Cluster '{CLUSTER_NAME}' not found in namespace {NS} after apply -- did you set "
            f"metadata.name: {CLUSTER_NAME}? (src/cluster.yaml is a TODO comment block that applies "
            "nothing until you replace it with a real Cluster CR)"
        )

    spec = cluster.get("spec", {})

    instances = spec.get("instances")
    if instances != EXPECTED_INSTANCES:
        not_passed(f"Cluster '{CLUSTER_NAME}' spec.instances={instances!r}, expected {EXPECTED_INSTANCES}")

    image = spec.get("imageName") or ""
    if not image.startswith(EXPECTED_IMAGE_PREFIX):
        not_passed(
            f"Cluster '{CLUSTER_NAME}' spec.imageName={image!r}, expected an image starting with "
            f"'{EXPECTED_IMAGE_PREFIX}'"
        )

    storage = spec.get("storage") or {}
    if not storage.get("size"):
        not_passed(f"Cluster '{CLUSTER_NAME}' spec.storage.size not set")
    storage_class = storage.get("storageClass")
    if storage_class not in (None, "standard"):
        not_passed(
            f"Cluster '{CLUSTER_NAME}' spec.storage.storageClass={storage_class!r}, expected "
            "'standard' (this cluster's default StorageClass) or unset"
        )


def _wait_cluster_ready(desc: str, timeout: int):
    def _check() -> bool:
        cluster = _get_cluster()
        status = cluster.get("status", {})
        return (
            status.get("instances") == EXPECTED_INSTANCES
            and status.get("readyInstances") == EXPECTED_INSTANCES
            and bool(status.get("currentPrimary"))
        )

    wait_until(_check, timeout=timeout, interval=10, desc=desc)


def _current_primary() -> str:
    cluster = _get_cluster()
    primary = cluster.get("status", {}).get("currentPrimary")
    if not primary:
        not_passed(f"Cluster '{CLUSTER_NAME}' status.currentPrimary not set")
    return primary


def _check_primary_label(primary_pod: str):
    pod = kubectl_json("get", "pod", primary_pod, ns=NS, check=False)
    if not pod:
        not_passed(f"primary pod '{primary_pod}' (per status.currentPrimary) not found")
    role = pod.get("metadata", {}).get("labels", {}).get("cnpg.io/instanceRole")
    if role != "primary":
        not_passed(
            f"pod '{primary_pod}' is status.currentPrimary but its cnpg.io/instanceRole label "
            f"is {role!r}, expected 'primary'"
        )


def _force_delete_pod(name: str):
    result = kubectl(
        "delete", "pod", name, "--grace-period=0", "--force", ns=NS, check=False, timeout=60,
    )
    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"force-deleting primary pod '{name}' failed: {err}")


REQUIRED_SECTIONS = [
    "StatefulSets vs Deployments",
    "Failover observations",
    "Why databases on Kubernetes are hard",
]

KEYWORDS = [
    "stable identity", "stable network identity", "ordinal",
    "PVC per replica", "PVC-per-replica", "persistent volume claim",
    "ordered", "sequential", "headless service", "quorum", "failover",
    "primary", "replica", "StatefulSet",
]


def _check_notes():
    sections = check_sections(NOTES, REQUIRED_SECTIONS, min_chars=250)
    full_text = "\n\n".join(sections.values())
    check_keywords(full_text, KEYWORDS, min_hits=7, label="NOTES.md")


@guarded
def main():
    require_cluster()
    _require_cnpg_operator()

    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _apply_cluster()
        _check_cluster_spec()
        _wait_cluster_ready(
            desc=f"Cluster '{CLUSTER_NAME}' to reach {EXPECTED_INSTANCES}/{EXPECTED_INSTANCES} ready instances",
            timeout=CLUSTER_READY_TIMEOUT_S,
        )

        old_primary = _current_primary()
        _check_primary_label(old_primary)
        _force_delete_pod(old_primary)

        def _failover_done() -> bool:
            cluster = _get_cluster()
            status = cluster.get("status", {})
            new_primary = status.get("currentPrimary")
            return (
                bool(new_primary)
                and new_primary != old_primary
                and status.get("instances") == EXPECTED_INSTANCES
                and status.get("readyInstances") == EXPECTED_INSTANCES
            )

        wait_until(
            _failover_done,
            timeout=FAILOVER_TIMEOUT_S,
            interval=5,
            desc=(
                f"a new primary to be elected (old primary was '{old_primary}') and the cluster "
                f"to return to {EXPECTED_INSTANCES}/{EXPECTED_INSTANCES} ready"
            ),
        )
        new_primary = _current_primary()

        _check_notes()

        passed(
            f"Cluster '{CLUSTER_NAME}' reached {EXPECTED_INSTANCES}/{EXPECTED_INSTANCES} ready instances; "
            f"forced deletion of primary '{old_primary}' resulted in new primary '{new_primary}' and "
            "the cluster returned to fully-ready; NOTES.md complete"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
