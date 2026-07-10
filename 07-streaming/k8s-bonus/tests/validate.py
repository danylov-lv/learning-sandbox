"""Validator for k8s-bonus. Offline-first.

Always run (offline section, requires only `helm` on PATH):
  - `helm template` renders src/helm/price-consumer/ without error.
  - The rendered manifests contain:
      * a Deployment whose first container sets BOTH resources.requests
        and resources.limits with cpu and memory. If they are exactly the
        classic copy-paste defaults (cpu 100m, memory 128Mi), that is a
        WARNING with a pointed question, not a failure — measured numbers
        can legitimately land there, it's just rare;
      * a HorizontalPodAutoscaler (autoscaling/v2) whose
        spec.scaleTargetRef names that Deployment, with minReplicas,
        maxReplicas, and at least one entry in spec.metrics;
      * a PodDisruptionBudget whose selector matches the Deployment's
        pod labels and sets minAvailable or maxUnavailable.
  - `helm lint` exits 0.

Live section (OPTIONAL — auto-skipped with a notice, never a failure,
when no kind cluster is reachable via kubectl):
  - a helm release of this chart is installed somewhere in the cluster.

Run from the k8s-bonus directory:

    uv run python tests/validate.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

CHART_DIR = TASK_ROOT / "src" / "helm" / "price-consumer"
COPY_PASTE_DEFAULTS = {"cpu": "100m", "memory": "128Mi"}


def _run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _require_helm():
    if shutil.which("helm") is None:
        not_passed(
            "`helm` not found on PATH — this bonus's validator renders the chart offline "
            "with `helm template` and needs helm installed (https://helm.sh/docs/intro/install/)"
        )


def _render_chart():
    result = _run(["helm", "template", "price-consumer-test", str(CHART_DIR)])
    if result.returncode != 0:
        not_passed(f"`helm template` failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}")
    import yaml

    docs = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict)]
    return docs


def _find(docs, kind):
    return [d for d in docs if d.get("kind") == kind]


def check_deployment(docs, failures, warnings):
    deployments = _find(docs, "Deployment")
    if not deployments:
        failures.append("no Deployment in rendered chart")
        return None
    dep = deployments[0]
    containers = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        failures.append("Deployment has no containers")
        return dep
    resources = containers[0].get("resources") or {}
    for section in ("requests", "limits"):
        values = resources.get(section) or {}
        for key in ("cpu", "memory"):
            if not values.get(key):
                failures.append(f"Deployment container resources.{section}.{key} is not set")
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}
    if (
        requests.get("cpu") == COPY_PASTE_DEFAULTS["cpu"]
        and requests.get("memory") == COPY_PASTE_DEFAULTS["memory"]
    ) or (
        limits.get("cpu") == COPY_PASTE_DEFAULTS["cpu"]
        and limits.get("memory") == COPY_PASTE_DEFAULTS["memory"]
    ):
        warnings.append(
            "resources are exactly 100m/128Mi — the copy-paste default. Did you actually "
            "measure the consumer (kubectl top / docker stats), or did muscle memory type "
            "that? If measured, the numbers belong in values.yaml comments; carry on."
        )
    return dep


def check_hpa(docs, failures, dep):
    hpas = _find(docs, "HorizontalPodAutoscaler")
    if not hpas:
        failures.append("no HorizontalPodAutoscaler in rendered chart")
        return
    hpa = hpas[0]
    if hpa.get("apiVersion") != "autoscaling/v2":
        failures.append(
            f"HPA apiVersion is {hpa.get('apiVersion')!r}, expected autoscaling/v2 "
            f"(the v2 metrics array shape is what the checks below assume)"
        )
    spec = hpa.get("spec", {})
    target = spec.get("scaleTargetRef") or {}
    if target.get("kind") != "Deployment":
        failures.append(f"HPA scaleTargetRef.kind is {target.get('kind')!r}, expected Deployment")
    dep_name = (dep or {}).get("metadata", {}).get("name")
    if dep_name and target.get("name") != dep_name:
        failures.append(
            f"HPA scaleTargetRef.name {target.get('name')!r} does not match the Deployment's "
            f"name {dep_name!r} — this HPA scales nothing"
        )
    if not isinstance(spec.get("minReplicas"), int):
        failures.append("HPA spec.minReplicas is not set to an integer")
    if not isinstance(spec.get("maxReplicas"), int):
        failures.append("HPA spec.maxReplicas is not set to an integer")
    if isinstance(spec.get("minReplicas"), int) and isinstance(spec.get("maxReplicas"), int):
        if spec["maxReplicas"] < spec["minReplicas"]:
            failures.append("HPA maxReplicas is less than minReplicas")
    metrics = spec.get("metrics") or []
    if not metrics:
        failures.append("HPA spec.metrics is empty — needs at least one metric")


def check_pdb(docs, failures, dep):
    pdbs = _find(docs, "PodDisruptionBudget")
    if not pdbs:
        failures.append("no PodDisruptionBudget in rendered chart")
        return
    if dep is None:
        return
    pdb = pdbs[0]
    selector = (pdb.get("spec", {}).get("selector") or {}).get("matchLabels") or {}
    if not selector:
        failures.append("PDB has no spec.selector.matchLabels")
        return
    pod_labels = (
        dep.get("spec", {}).get("template", {}).get("metadata", {}).get("labels") or {}
    )
    if not all(pod_labels.get(k) == v for k, v in selector.items()):
        failures.append(
            f"PDB selector {selector} does not match the Deployment's pod labels {pod_labels} "
            f"— this PDB protects nothing"
        )
    spec = pdb.get("spec", {})
    if "minAvailable" not in spec and "maxUnavailable" not in spec:
        failures.append("PDB sets neither minAvailable nor maxUnavailable")


def check_lint(failures):
    result = _run(["helm", "lint", str(CHART_DIR)])
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()
        failures.append("`helm lint` failed: " + (tail[-1] if tail else "unknown error"))


def live_section():
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        print("NOTICE: kubectl not found — skipping the optional live-cluster section.")
        return
    try:
        probe = _run(["kubectl", "cluster-info", "--request-timeout=3s"], timeout=15)
    except subprocess.TimeoutExpired:
        probe = None
    if probe is None or probe.returncode != 0:
        print("NOTICE: no reachable cluster — skipping the optional live-cluster section.")
        return

    result = _run(["helm", "list", "-A", "-o", "json"])
    releases = []
    if result.returncode == 0:
        try:
            releases = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            releases = []
    ours = [r for r in releases if str(r.get("chart", "")).startswith("price-consumer")]
    if ours:
        print(f"live: found installed release(s): {[r.get('name') for r in ours]}")
    else:
        print(
            "NOTICE: cluster reachable but no price-consumer release installed — the live "
            "check only reports, it does not fail. Install with `helm install` into your "
            "kind cluster to exercise it, then `kubectl scale deployment ... --replicas=N` "
            "and watch the rebalance."
        )


@guarded
def main():
    _require_helm()

    if not CHART_DIR.exists():
        not_passed(f"chart directory not found at {CHART_DIR}")

    docs = _render_chart()
    if not docs:
        not_passed(
            "chart rendered zero manifests — templates/ is still empty. Write the "
            "Deployment, HorizontalPodAutoscaler and PodDisruptionBudget templates first."
        )

    failures = []
    warnings = []

    dep = check_deployment(docs, failures, warnings)
    check_hpa(docs, failures, dep)
    check_pdb(docs, failures, dep)
    check_lint(failures)

    for w in warnings:
        print(f"WARNING: {w}")

    if failures:
        not_passed("; ".join(failures[:6]) + (f" (+{len(failures) - 6} more)" if len(failures) > 6 else ""))

    live_section()

    passed("chart renders, lints, and contains a resource-bounded Deployment, a matching "
           "HPA, and a matching PDB")


if __name__ == "__main__":
    main()
