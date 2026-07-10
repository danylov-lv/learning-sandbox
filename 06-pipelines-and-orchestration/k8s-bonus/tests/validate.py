"""Validator for k8s-bonus. Offline-first.

Always run (offline section, requires only `helm` on PATH):
  - `helm template` renders src/helm/price-pipeline/ without error.
  - The rendered manifests contain:
      * a CronJob with a non-empty spec.schedule and a non-empty container
        image;
      * a Deployment whose first container sets BOTH resources.requests
        and resources.limits with cpu and memory. If they are exactly the
        classic copy-paste defaults (cpu 100m, memory 128Mi), that is a
        WARNING with a pointed question, not a failure — measured numbers
        can legitimately land there, it's just rare;
      * a PodDisruptionBudget whose selector matches the Deployment's
        pod labels.
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

CHART_DIR = TASK_ROOT / "src" / "helm" / "price-pipeline"
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
    result = _run(["helm", "template", "price-pipeline-test", str(CHART_DIR)])
    if result.returncode != 0:
        not_passed(f"`helm template` failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}")
    import yaml

    docs = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict)]
    return docs


def _find(docs, kind):
    return [d for d in docs if d.get("kind") == kind]


def check_cronjob(docs, failures):
    cronjobs = _find(docs, "CronJob")
    if not cronjobs:
        failures.append("no CronJob in rendered chart")
        return
    cj = cronjobs[0]
    schedule = cj.get("spec", {}).get("schedule")
    if not schedule or not str(schedule).strip():
        failures.append("CronJob has no spec.schedule")
    containers = (
        cj.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    if not containers or not containers[0].get("image"):
        failures.append("CronJob's job template has no container image set")


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
            "measure the monitor (kubectl top / docker stats), or did muscle memory type "
            "that? If measured, the numbers belong in values.yaml comments; carry on."
        )
    return dep


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
    ours = [r for r in releases if str(r.get("chart", "")).startswith("price-pipeline")]
    if ours:
        print(f"live: found installed release(s): {[r.get('name') for r in ours]}")
    else:
        print(
            "NOTICE: cluster reachable but no price-pipeline release installed — the live "
            "check only reports, it does not fail. Install with `helm install` into your "
            "kind cluster to exercise it."
        )


@guarded
def main():
    _require_helm()

    if not CHART_DIR.exists():
        not_passed(f"chart directory not found at {CHART_DIR}")

    docs = _render_chart()
    if not docs:
        not_passed(
            "chart rendered zero manifests — templates/ is still empty. Write the CronJob, "
            "Deployment and PDB templates first."
        )

    failures = []
    warnings = []

    check_cronjob(docs, failures)
    dep = check_deployment(docs, failures, warnings)
    check_pdb(docs, failures, dep)
    check_lint(failures)

    for w in warnings:
        print(f"WARNING: {w}")

    if failures:
        not_passed("; ".join(failures[:6]) + (f" (+{len(failures) - 6} more)" if len(failures) > 6 else ""))

    live_section()

    passed("chart renders, lints, and contains a scheduled CronJob, a resource-bounded "
           "Deployment, and a matching PDB")


if __name__ == "__main__":
    main()
