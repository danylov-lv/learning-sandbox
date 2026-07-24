"""Validator for 20-kubernetes task 18, checkpoint 1 (app-of-apps).

Run from this task directory:

    uv run python tests/validate_cp1.py

Requires Argo CD + Gitea already installed cluster-wide (owned by task 16 --
run 16-argocd-app-by-hand/scripts/install.sh if this fails with a clear
message saying so; this checkpoint never installs or reinstalls anything).

What it does:
  1. Parses src/apps/*.yaml as Argo CD Application manifests. Expects
     exactly 2 distinct, valid, non-stub Application docs, each targeting
     destination namespace t18 (anti-cheat + non-vacuous: an unfilled
     TODO stub parses to zero Applications).
  2. Parses src/root-app.yaml as the PARENT Application. Checks its own
     spec directly: repoURL/path point at the seeded sandbox20/t18-apps.git
     repo, destination is argocd (children are Application CRs, which must
     live where Argo CD watches them), syncPolicy is set.
  3. Seeds sandbox20/t18-child-chart.git (a small fixture chart, given/
     child-chart/ -- not learner-authored) if it doesn't already exist.
  4. Pushes src/apps/*.yaml into sandbox20/t18-apps.git (force, fresh
     history every run -- this repo belongs entirely to this checkpoint).
  5. Deletes any stale Applications from a previous run, applies
     src/root-app.yaml, and waits (bounded) for the two expected child
     Applications to appear -- proof the PARENT actually spawned them,
     since this validator never applies the children directly itself.
  6. Nudges parent + each child to sync, waits for all three to reach
     Synced/Healthy, and confirms each child's chart landed a ready
     Deployment in namespace t18.

Cleans up its own Applications (root + both children, cascade) at the end
either way. Never deletes namespace t18 outright (task 18's cp2 shares
it) and never touches Argo CD/Gitea themselves or task 16's repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

import yaml  # noqa: E402

from harness.common import (  # noqa: E402
    ensure_ns,
    guarded,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    port_forward,
    require_cluster,
    wait_until,
)

import gitea  # noqa: E402

NS = "t18"
ARGOCD_NS = "argocd"

ROOT_APP_SRC = TASK_ROOT / "src" / "root-app.yaml"
APPS_DIR = TASK_ROOT / "src" / "apps"

ROOT_APP_NAME = "t18-root"
EXPECTED_CHILD_NAMES = ["t18-child-a", "t18-child-b"]

APPS_REPO = "t18-apps"
CHILD_CHART_REPO = "t18-child-chart"
CHILD_CHART_DIR = TASK_ROOT / "given" / "child-chart"

EXPECTED_APPS_REPO_FRAGMENT = f"{gitea.GITEA_ORG}/{APPS_REPO}"
EXPECTED_CHILD_CHART_REPO_FRAGMENT = f"{gitea.GITEA_ORG}/{CHILD_CHART_REPO}"
EXPECTED_GITEA_HOST_FRAGMENT = "gitea-http.argocd.svc"
EXPECTED_DESTINATION_SERVER = "https://kubernetes.default.svc"

APPEAR_TIMEOUT_S = 90
SYNC_TIMEOUT_S = 300


def _require_argocd_and_gitea():
    for kind, name in (("deployment", "argocd-server"), ("deployment", "argocd-repo-server")):
        d = kubectl_json("get", kind, name, ns=ARGOCD_NS, check=False)
        if not d or not d.get("status", {}).get("readyReplicas", 0):
            not_passed(
                f"Argo CD is not installed/ready (no ready '{name}' Deployment in namespace "
                f"'{ARGOCD_NS}') -- run 16-argocd-app-by-hand/scripts/install.sh first"
            )
    sts = kubectl_json("get", "statefulset", "argocd-application-controller", ns=ARGOCD_NS, check=False)
    if not sts or not sts.get("status", {}).get("readyReplicas", 0):
        not_passed(
            "Argo CD application-controller StatefulSet is not ready -- run "
            "16-argocd-app-by-hand/scripts/install.sh first"
        )
    gitea_dep = kubectl_json("get", "deployment", "gitea", ns=ARGOCD_NS, check=False)
    if not gitea_dep or not gitea_dep.get("status", {}).get("readyReplicas", 0):
        not_passed(
            "Gitea is not installed/ready (no ready 'gitea' Deployment in namespace "
            f"'{ARGOCD_NS}') -- run 16-argocd-app-by-hand/scripts/install.sh first"
        )


def _load_application_doc(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    except yaml.YAMLError:
        return None
    if len(docs) != 1:
        return None
    doc = docs[0]
    if not isinstance(doc, dict):
        return None
    if doc.get("apiVersion") != "argoproj.io/v1alpha1" or doc.get("kind") != "Application":
        return None
    if not doc.get("metadata", {}).get("name"):
        return None
    return doc


def _parse_child_apps() -> dict:
    """Returns {name: doc} for every valid, distinctly-named child
    Application found under src/apps/. A TODO-only stub file contributes
    nothing (non-vacuous: 0 valid docs fails cleanly below)."""
    found = {}
    for path in sorted(APPS_DIR.glob("*.yaml")):
        doc = _load_application_doc(path)
        if doc is None:
            continue
        name = doc["metadata"]["name"]
        found[name] = doc
    return found


def _check_child_specs(children: dict):
    if len(children) != 2:
        not_passed(
            f"expected exactly 2 valid child Application manifests under src/apps/, found "
            f"{len(children)} ({', '.join(sorted(children)) or 'none'}) -- each file must be a real "
            "Application manifest (apiVersion: argoproj.io/v1alpha1, kind: Application) with its own "
            "metadata.name; an unfilled TODO stub contributes nothing"
        )
    for name, doc in children.items():
        spec = doc.get("spec", {})
        source = spec.get("source") or (spec.get("sources") or [{}])[0]
        repo_url = source.get("repoURL", "")
        if EXPECTED_GITEA_HOST_FRAGMENT not in repo_url:
            not_passed(
                f"child Application '{name}' spec.source.repoURL={repo_url!r} does not point at the "
                f"in-cluster Gitea Service (expected it to contain {EXPECTED_GITEA_HOST_FRAGMENT!r})"
            )
        destination = spec.get("destination", {})
        if destination.get("namespace") != NS:
            not_passed(
                f"child Application '{name}' spec.destination.namespace="
                f"{destination.get('namespace')!r}, expected {NS!r}"
            )
        if not spec.get("syncPolicy"):
            not_passed(f"child Application '{name}' has no spec.syncPolicy set")


def _check_root_spec(doc: dict):
    name = doc.get("metadata", {}).get("name")
    if name != ROOT_APP_NAME:
        not_passed(
            f"src/root-app.yaml metadata.name={name!r}, expected {ROOT_APP_NAME!r}"
        )
    if doc.get("metadata", {}).get("namespace") != ARGOCD_NS:
        not_passed(
            f"src/root-app.yaml metadata.namespace={doc.get('metadata', {}).get('namespace')!r}, "
            f"expected {ARGOCD_NS!r} (Argo CD only watches Application objects in its own namespace)"
        )
    spec = doc.get("spec", {})
    source = spec.get("source") or (spec.get("sources") or [{}])[0]
    repo_url = source.get("repoURL", "")
    if EXPECTED_GITEA_HOST_FRAGMENT not in repo_url or EXPECTED_APPS_REPO_FRAGMENT not in repo_url:
        not_passed(
            f"src/root-app.yaml spec.source.repoURL={repo_url!r} does not point at the seeded "
            f"sandbox20/{APPS_REPO} repo (expected it to contain both {EXPECTED_GITEA_HOST_FRAGMENT!r} "
            f"and {EXPECTED_APPS_REPO_FRAGMENT!r})"
        )
    path = source.get("path", "")
    if path not in (".", "", None):
        not_passed(f"src/root-app.yaml spec.source.path={path!r}, expected '.' -- src/apps/ is pushed to the repo root")
    destination = spec.get("destination", {})
    if destination.get("server") != EXPECTED_DESTINATION_SERVER and destination.get("name") not in ("in-cluster",):
        not_passed(
            f"src/root-app.yaml spec.destination.server={destination.get('server')!r}, expected "
            f"{EXPECTED_DESTINATION_SERVER!r}"
        )
    if destination.get("namespace") != ARGOCD_NS:
        not_passed(
            f"src/root-app.yaml spec.destination.namespace={destination.get('namespace')!r}, expected "
            f"{ARGOCD_NS!r} -- the parent Application's own output is a set of Application objects, "
            "which must be applied into argocd, not t18"
        )
    if not spec.get("syncPolicy"):
        not_passed("src/root-app.yaml has no spec.syncPolicy set")


def _seed_child_chart_repo(local_port: int):
    gitea.ensure_repo(local_port, CHILD_CHART_REPO)
    if not gitea.list_commits(local_port, CHILD_CHART_REPO):
        gitea.push_initial(
            local_port, CHILD_CHART_REPO, CHILD_CHART_DIR,
            "seed: t18-child fixture chart (image 1.0)",
        )


def _push_apps_dir(local_port: int):
    gitea.ensure_repo(local_port, APPS_REPO)
    gitea.push_initial(
        local_port, APPS_REPO, APPS_DIR,
        "cp1: push learner's src/apps/ (validator run)",
    )


def _delete_stale_applications():
    for name in [ROOT_APP_NAME] + EXPECTED_CHILD_NAMES:
        kubectl("delete", "application.argoproj.io", name, ns=ARGOCD_NS, check=False, timeout=60)


def _apply_root_app():
    result = kubectl("apply", "-f", str(ROOT_APP_SRC), ns=ARGOCD_NS, check=False, timeout=60)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(
            f"kubectl apply -f src/root-app.yaml failed: {detail} (src/root-app.yaml is a TODO comment "
            "block that applies nothing until you replace it with a real Application)"
        )


def _wait_children_appear():
    def _check():
        for name in EXPECTED_CHILD_NAMES:
            app = kubectl_json("get", "application.argoproj.io", name, ns=ARGOCD_NS, check=False)
            if not app:
                return False
        return True

    wait_until(
        _check, timeout=APPEAR_TIMEOUT_S, interval=3,
        desc=(
            f"parent Application '{ROOT_APP_NAME}' to spawn child Applications "
            f"{EXPECTED_CHILD_NAMES} (never applied directly by this validator -- only Argo CD "
            "reconciling your root-app.yaml creates them)"
        ),
    )


def _trigger_sync(name: str):
    patch = (
        '{"operation":{"initiatedBy":{"username":"validator"},'
        '"sync":{"syncStrategy":{"hook":{}}}}}'
    )
    kubectl("patch", "application", name, "--type", "merge", "-p", patch, ns=ARGOCD_NS, check=False, timeout=30)


def _wait_synced_and_healthy(name: str):
    def _check():
        app = kubectl_json("get", "application.argoproj.io", name, ns=ARGOCD_NS, check=False)
        if not app:
            return False
        status = app.get("status", {})
        return (
            status.get("sync", {}).get("status") == "Synced"
            and status.get("health", {}).get("status") == "Healthy"
        )

    wait_until(
        _check, timeout=SYNC_TIMEOUT_S, interval=5,
        desc=f"Application '{name}' to reach sync.status=Synced and health.status=Healthy",
    )


def _check_workloads():
    deployments = kubectl_json("get", "deployment", "-l", "app.kubernetes.io/name=t18-child", ns=NS, check=False)
    items = deployments.get("items", []) if deployments else []
    names = [d["metadata"]["name"] for d in items]
    if len(items) < 2:
        not_passed(
            f"expected at least 2 Deployments labeled app.kubernetes.io/name=t18-child in namespace "
            f"'{NS}' (one per child Application), found {len(items)} ({', '.join(names) or 'none'})"
        )
    not_ready = [d["metadata"]["name"] for d in items if not d.get("status", {}).get("readyReplicas", 0)]
    if not_ready:
        not_passed(f"Deployment(s) with no ready replicas in namespace '{NS}': {', '.join(not_ready)}")
    for expected_name in EXPECTED_CHILD_NAMES:
        if not any(expected_name in n for n in names):
            not_passed(
                f"no Deployment name in namespace '{NS}' contains '{expected_name}' -- Argo CD uses the "
                "child Application's own name as the Helm release name, so each child should render a "
                "distinctly-named Deployment"
            )


@guarded
def main():
    require_cluster()
    _require_argocd_and_gitea()

    children = _parse_child_apps()
    _check_child_specs(children)

    if not ROOT_APP_SRC.exists():
        not_passed(f"expected file not found: {ROOT_APP_SRC}")
    root_doc = _load_application_doc(ROOT_APP_SRC)
    if root_doc is None:
        not_passed(
            "src/root-app.yaml is not a valid single-document Argo CD Application manifest -- it is a "
            "TODO comment block until you replace it with a real Application"
        )
    _check_root_spec(root_doc)

    ensure_ns(NS)

    with port_forward("svc/gitea-http", 3000, ARGOCD_NS) as local_port:
        _seed_child_chart_repo(local_port)
        _push_apps_dir(local_port)

    _delete_stale_applications()

    try:
        _apply_root_app()
        _wait_children_appear()

        for name in [ROOT_APP_NAME] + EXPECTED_CHILD_NAMES:
            _trigger_sync(name)
        for name in [ROOT_APP_NAME] + EXPECTED_CHILD_NAMES:
            _wait_synced_and_healthy(name)

        _check_workloads()

        passed(
            f"parent Application '{ROOT_APP_NAME}' spawned child Applications {EXPECTED_CHILD_NAMES}, "
            f"all reached Synced/Healthy, and each landed a ready workload in namespace '{NS}'"
        )
    finally:
        _delete_stale_applications()


if __name__ == "__main__":
    main()
