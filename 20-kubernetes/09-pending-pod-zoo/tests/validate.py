"""Validator for 20-kubernetes task 09 (pending-pod-zoo).

Run from this task directory:

    uv run python tests/validate.py

Runs given/setup.sh fresh (recreates namespace t09, retaints
sandbox20-worker2 with s20-t09/quarantine=true:NoSchedule, applies the
zoo), waits for all five pods to be Pending, and asserts each shows its
expected FailedScheduling/PVC-binding signature in events -- a non-vacuous
gate proving the fixture is actually broken the way the task claims before
any credit is given. Then deletes the five original pods (+ PVC) and
applies the learner's fixes/*.yaml, asserting all five reach Running/Ready:
pod-d must land on sandbox20-worker2 with the quarantine taint still on the
node and a matching toleration still present in its spec (anti-cheat: it
must not have dropped the worker2 nodeSelector), and pod-e's PVC must be
Bound. Finally checks DIAGNOSIS.md via the shared doc-gate helpers.

Namespace t09 is deleted and the quarantine taint is removed from
sandbox20-worker2 at the end, whether this passes or fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
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

NS = "t09"
CONTEXT = "kind-sandbox20"
NODE = "sandbox20-worker2"
TAINT_KEY = "s20-t09/quarantine"

GIVEN_DIR = TASK_ROOT / "given"
FIXES_DIR = TASK_ROOT / "fixes"
DIAGNOSIS_PATH = TASK_ROOT / "DIAGNOSIS.md"

POD_NAMES = ["pod-a", "pod-b", "pod-c", "pod-d", "pod-e"]

# Substring(s) expected in this pod's aggregated FailedScheduling event
# message once the zoo fixture is freshly applied. Order-independent, all
# must be present (case-sensitive, matches actual scheduler wording on
# Kubernetes 1.32).
EXPECTED_EVENT_SIGNATURES = {
    "pod-a": ["Insufficient cpu"],
    "pod-b": ["didn't match Pod's node affinity/selector"],
    "pod-c": ["didn't match Pod's node affinity/selector"],
    "pod-d": ["untolerated taint {s20-t09/quarantine"],
    "pod-e": ["unbound immediate PersistentVolumeClaims"],
}

STUB_MARKERS = ("TODO(you)",)

DIAGNOSIS_KEYWORDS = [
    "FailedScheduling",
    "Insufficient",
    "affinity",
    "taint",
    "toleration",
    "unbound",
    "storage class",
]


def _apply_taint():
    kubectl("taint", "node", NODE, f"{TAINT_KEY}=true:NoSchedule", "--overwrite", timeout=30)


def _seed_fixture():
    """Equivalent of given/setup.sh, done directly rather than shelling out to
    a bash script (keeps this validator portable across the learner's shell).
    Recreates namespace t09, retaints sandbox20-worker2, applies the zoo."""
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    _apply_taint()
    result = kubectl("apply", "-f", str(GIVEN_DIR / "zoo.yaml"), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f given/zoo.yaml failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _remove_taint():
    kubectl("taint", "node", NODE, f"{TAINT_KEY}:NoSchedule-", check=False, timeout=30)


def _node_taint_present() -> bool:
    node = kubectl_json("get", "node", NODE, check=False)
    taints = node.get("spec", {}).get("taints", [])
    return any(t.get("key") == TAINT_KEY for t in taints)


def _pod_events_text(name: str) -> str:
    result = kubectl(
        "get", "events",
        "--field-selector", f"involvedObject.name={name}",
        "-o", "jsonpath={range .items[*]}{.reason}: {.message}\n{end}",
        ns=NS, check=False,
    )
    return result.stdout


def _pvc_events_text(name: str) -> str:
    result = kubectl(
        "get", "events",
        "--field-selector", f"involvedObject.name={name}",
        "-o", "jsonpath={range .items[*]}{.reason}: {.message}\n{end}",
        ns=NS, check=False,
    )
    return result.stdout


def _pod_phase(name: str) -> str:
    data = kubectl_json("get", "pod", name, ns=NS, check=False)
    return data.get("status", {}).get("phase", "")


def _verify_fixture_non_vacuous():
    def _all_pending():
        for name in POD_NAMES:
            if _pod_phase(name) != "Pending":
                return False
        return True

    wait_until(_all_pending, timeout=60, interval=2, desc="all five zoo pods to be Pending")

    missing = []
    for name in POD_NAMES:
        text = _pod_events_text(name)
        for needle in EXPECTED_EVENT_SIGNATURES[name]:
            if needle not in text:
                missing.append(f"{name}: expected event text containing {needle!r}, got: {text.strip()!r}")

    pvc_text = _pvc_events_text("zoo-data")
    if "fast-ssd" not in pvc_text and "not found" not in pvc_text:
        missing.append(f"zoo-data PVC: expected a ProvisioningFailed/storage-class-not-found event, got: {pvc_text.strip()!r}")

    if missing:
        not_passed("fixture did not reproduce the expected Pending signatures -- " + "; ".join(missing))


def _check_fixes_not_stub():
    for name in POD_NAMES:
        path = FIXES_DIR / f"{name}.yaml"
        if not path.exists():
            not_passed(f"missing {path}")
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in STUB_MARKERS):
            not_passed(f"{path} still looks like the unfilled TODO stub")


def _delete_originals():
    kubectl("delete", "pod", *POD_NAMES, ns=NS, check=False, timeout=60)
    kubectl("delete", "pvc", "zoo-data", ns=NS, check=False, timeout=60)


def _apply_fixes():
    args = ["apply"]
    for name in POD_NAMES:
        args += ["-f", str(FIXES_DIR / f"{name}.yaml")]
    result = kubectl(*args, ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f fixes/ failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _wait_all_running():
    def _ready():
        for name in POD_NAMES:
            data = kubectl_json("get", "pod", name, ns=NS, check=False)
            if not data:
                return False
            phase = data.get("status", {}).get("phase")
            conditions = {c["type"]: c["status"] for c in data.get("status", {}).get("conditions", [])}
            if phase != "Running" or conditions.get("Ready") != "True":
                return False
        return True

    wait_until(_ready, timeout=120, interval=3, desc="all five fixed pods to reach Running/Ready")


def _check_pod_d_placement():
    data = kubectl_json("get", "pod", "pod-d", ns=NS, check=False)
    if not data:
        not_passed("pod-d not found after applying fixes/")

    node_name = data.get("spec", {}).get("nodeName")
    if node_name != NODE:
        not_passed(f"pod-d scheduled onto {node_name!r}, expected {NODE!r} -- did you drop the worker2 nodeSelector?")

    node_selector = data.get("spec", {}).get("nodeSelector", {})
    if node_selector.get("kubernetes.io/hostname") != NODE:
        not_passed(
            f"pod-d spec.nodeSelector={node_selector!r} no longer pins kubernetes.io/hostname: {NODE} -- "
            "the fix for pod-d is adding a toleration, not removing the node constraint"
        )

    tolerations = data.get("spec", {}).get("tolerations", [])
    matching = [
        t for t in tolerations
        if t.get("key") == TAINT_KEY
        and t.get("effect") == "NoSchedule"
        and t.get("operator", "Equal") in ("Equal", "Exists")
    ]
    if not matching:
        not_passed(
            f"pod-d spec.tolerations={tolerations!r} has no toleration for {TAINT_KEY}:NoSchedule -- "
            "that's the actual fix this pod needs"
        )

    if not _node_taint_present():
        not_passed(
            f"the {TAINT_KEY} taint is no longer on {NODE} -- pod-d must schedule with the taint still "
            "in place (via a toleration), not because the taint disappeared"
        )


def _check_pod_e_pvc():
    pvc = kubectl_json("get", "pvc", "zoo-data", ns=NS, check=False)
    if not pvc:
        not_passed("PVC zoo-data not found after applying fixes/")
    phase = pvc.get("status", {}).get("phase")
    if phase != "Bound":
        not_passed(f"PVC zoo-data status.phase={phase!r}, expected Bound")

    pod = kubectl_json("get", "pod", "pod-e", ns=NS, check=False)
    volumes = pod.get("spec", {}).get("volumes", [])
    claims = [v for v in volumes if v.get("persistentVolumeClaim", {}).get("claimName") == "zoo-data"]
    if not claims:
        not_passed("pod-e no longer mounts the zoo-data PVC -- fix the PVC's storageClassName, don't drop the mount")


def _check_diagnosis():
    sections = check_sections(
        DIAGNOSIS_PATH,
        required=["pod-a", "pod-b", "pod-c", "pod-d", "pod-e"],
        min_chars=120,
    )
    for name in POD_NAMES:
        body = sections[name]
        lowered = body.lower()
        hit = any(kw.lower() in lowered for kw in DIAGNOSIS_KEYWORDS)
        if not hit:
            not_passed(
                f"DIAGNOSIS.md section '{name}' doesn't mention any scheduler-event vocabulary "
                f"({', '.join(DIAGNOSIS_KEYWORDS)}) -- ground this in what you actually saw, not generic prose"
            )


@guarded
def main():
    require_cluster()
    try:
        _seed_fixture()
        _verify_fixture_non_vacuous()
        _check_fixes_not_stub()
        _delete_originals()
        _apply_fixes()
        _wait_all_running()
        _check_pod_d_placement()
        _check_pod_e_pvc()
        _check_diagnosis()
        passed(
            "all five pods diagnosed and fixed: pod-a/b/c/e running, pod-d running on sandbox20-worker2 "
            "with the quarantine taint still present and tolerated, zoo-data PVC Bound"
        )
    finally:
        delete_ns(NS, wait=False)
        _remove_taint()


if __name__ == "__main__":
    main()
