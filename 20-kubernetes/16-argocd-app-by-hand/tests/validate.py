"""Validator for 20-kubernetes task 16 (argocd-app-by-hand).

Run from this task directory:

    uv run python tests/validate.py

Requires Argo CD + Gitea already installed cluster-wide (scripts/install.sh
-- this task owns that install; it is NOT reinstalled or uninstalled here).
Confirms the seeded Gitea repo (given/chart/ pushed by the install script)
is reachable, applies the learner's src/application.yaml into namespace
argocd, inspects the Application's own spec (anti-cheat: repoURL/path/
destination must actually point at the in-cluster Gitea repo and namespace
t16, not just "an Application exists"), nudges Argo CD to sync it, and
waits (bounded) for status.sync.status == Synced and status.health.status
== Healthy. Finally confirms the chart's workload actually landed in t16.

The learner's Application is deleted from argocd and namespace t16 is
deleted at the end whether this passes or fails. Argo CD + Gitea themselves
are left installed -- this task owns that install, later tasks depend on
it.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

import requests  # noqa: E402

from harness.common import (  # noqa: E402
    delete_ns,
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

NS = "t16"
ARGOCD_NS = "argocd"
APP_SRC = TASK_ROOT / "src" / "application.yaml"
APP_NAME = "t16-app"

ARGOCD_SERVER_DEPLOYMENT = "argocd-server"
ARGOCD_REPO_SERVER_DEPLOYMENT = "argocd-repo-server"
ARGOCD_APP_CONTROLLER_STATEFULSET = "argocd-application-controller"

GITEA_DEPLOYMENT = "gitea"
GITEA_ORG = "sandbox20"
GITEA_REPO = "platform-charts"
# What scripts/install.sh actually pushed the fixture chart to -- the
# contract the learner's Application must target. Anti-cheat: a learner
# pointing at some other (e.g. public GitHub) chart must fail here.
EXPECTED_REPO_HOST_FRAGMENT = "gitea-http.argocd.svc"
EXPECTED_REPO_PATH_FRAGMENT = f"{GITEA_ORG}/{GITEA_REPO}"
EXPECTED_DESTINATION_SERVER = "https://kubernetes.default.svc"
EXPECTED_DESTINATION_NS = NS
FIXTURE_CHART_LABEL_SELECTOR = "app.kubernetes.io/name=sandbox20-fixture"

SYNC_TIMEOUT_S = 300


def _require_argocd_and_gitea():
    for dep in (ARGOCD_SERVER_DEPLOYMENT, ARGOCD_REPO_SERVER_DEPLOYMENT):
        d = kubectl_json("get", "deployment", dep, ns=ARGOCD_NS, check=False)
        if not d:
            not_passed(
                f"Argo CD is not installed (no Deployment '{dep}' in namespace '{ARGOCD_NS}') -- "
                "run scripts/install.sh from this task directory first"
            )
        if not d.get("status", {}).get("readyReplicas", 0):
            not_passed(f"Argo CD Deployment '{dep}' has no ready replicas -- run scripts/install.sh and wait for it to finish")

    sts = kubectl_json("get", "statefulset", ARGOCD_APP_CONTROLLER_STATEFULSET, ns=ARGOCD_NS, check=False)
    if not sts:
        not_passed(
            f"Argo CD is not installed (no StatefulSet '{ARGOCD_APP_CONTROLLER_STATEFULSET}' in "
            f"namespace '{ARGOCD_NS}') -- run scripts/install.sh first"
        )
    if not sts.get("status", {}).get("readyReplicas", 0):
        not_passed(f"Argo CD StatefulSet '{ARGOCD_APP_CONTROLLER_STATEFULSET}' has no ready replicas -- run scripts/install.sh")

    gitea = kubectl_json("get", "deployment", GITEA_DEPLOYMENT, ns=ARGOCD_NS, check=False)
    if not gitea:
        not_passed(
            f"Gitea is not installed (no Deployment '{GITEA_DEPLOYMENT}' in namespace '{ARGOCD_NS}') -- "
            "run scripts/install.sh from this task directory first"
        )
    if not gitea.get("status", {}).get("readyReplicas", 0):
        not_passed(f"Gitea Deployment '{GITEA_DEPLOYMENT}' has no ready replicas -- run scripts/install.sh and wait for it to finish")


def _check_seeded_repo_reachable():
    """Confirms the fixture chart the install script pushed is actually
    reachable inside the cluster -- reached the same way Argo CD's
    repo-server would, via the in-cluster Service, not the host port-
    forward the install script used to seed it."""
    with port_forward(f"svc/{GITEA_DEPLOYMENT}-http", 3000, ARGOCD_NS) as local_port:
        url = f"http://127.0.0.1:{local_port}/api/v1/repos/{GITEA_ORG}/{GITEA_REPO}/contents/Chart.yaml"

        def _reachable():
            try:
                resp = requests.get(url, params={"ref": "main"}, timeout=5)
                return resp.status_code == 200
            except requests.RequestException:
                return False

        wait_until(
            _reachable, timeout=30, interval=2,
            desc=f"seeded Gitea repo {GITEA_ORG}/{GITEA_REPO} (Chart.yaml) to be reachable -- run scripts/install.sh if this never installed",
        )


def _apply_application():
    result = kubectl("apply", "-f", str(APP_SRC), ns=ARGOCD_NS, check=False, timeout=60)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(
            f"kubectl apply -f src/application.yaml failed: {detail} "
            "(src/application.yaml is a TODO comment block that applies nothing until you replace it "
            "with a real Application)"
        )


def _find_application():
    app = kubectl_json("get", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False)
    if not app:
        not_passed(
            f"Application '{APP_NAME}' not found in namespace '{ARGOCD_NS}' after applying "
            f"src/application.yaml -- did you set metadata.name: {APP_NAME} and metadata.namespace: "
            f"{ARGOCD_NS}?"
        )
    return app


def _check_application_spec(app: dict) -> str:
    name = app.get("metadata", {}).get("name")
    spec = app.get("spec", {})

    source = spec.get("source") or (spec.get("sources") or [{}])[0]
    repo_url = source.get("repoURL", "")
    if EXPECTED_REPO_HOST_FRAGMENT not in repo_url or EXPECTED_REPO_PATH_FRAGMENT not in repo_url:
        not_passed(
            f"Application '{name}' spec.source.repoURL={repo_url!r} does not point at the seeded "
            f"in-cluster Gitea repo (expected it to contain both {EXPECTED_REPO_HOST_FRAGMENT!r} and "
            f"{EXPECTED_REPO_PATH_FRAGMENT!r} -- see README.md for the exact repoURL to use, and run "
            "scripts/install.sh's output if you're unsure)"
        )

    path = source.get("path", "")
    if path not in (".", "", None):
        not_passed(
            f"Application '{name}' spec.source.path={path!r}, expected '.' -- the fixture chart was "
            "pushed to the repo root, not a subdirectory"
        )

    destination = spec.get("destination", {})
    dest_server = destination.get("server", "")
    dest_name = destination.get("name", "")
    if dest_server != EXPECTED_DESTINATION_SERVER and dest_name not in ("in-cluster",):
        not_passed(
            f"Application '{name}' spec.destination.server={dest_server!r}, expected "
            f"{EXPECTED_DESTINATION_SERVER!r} (the in-cluster API server -- this task deploys into the "
            "same cluster, not an external one)"
        )
    if destination.get("namespace") != EXPECTED_DESTINATION_NS:
        not_passed(
            f"Application '{name}' spec.destination.namespace={destination.get('namespace')!r}, expected "
            f"{EXPECTED_DESTINATION_NS!r}"
        )

    if not spec.get("syncPolicy"):
        not_passed(f"Application '{name}' has no spec.syncPolicy set -- see README.md for what's required")

    return name


def _trigger_sync(name: str):
    """Requests a sync the same way `argocd app sync` does under the hood
    -- setting the Application's own `operation` field -- so this works
    without needing the argocd CLI or an authenticated API session, and
    works regardless of whether the learner's syncPolicy is automated or
    manual."""
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
        sync_status = status.get("sync", {}).get("status")
        health_status = status.get("health", {}).get("status")
        return sync_status == "Synced" and health_status == "Healthy"

    wait_until(
        _check, timeout=SYNC_TIMEOUT_S, interval=5,
        desc=f"Application '{name}' to reach sync.status=Synced and health.status=Healthy",
    )


def _check_workload_in_namespace():
    deployments = kubectl_json("get", "deployment", "-l", FIXTURE_CHART_LABEL_SELECTOR, ns=NS, check=False)
    items = deployments.get("items", []) if deployments else []
    if not items:
        not_passed(
            f"no Deployment labeled '{FIXTURE_CHART_LABEL_SELECTOR}' found in namespace '{NS}' -- the "
            "Application reports Synced/Healthy but the chart's workload didn't actually land in "
            f"'{NS}' (wrong spec.destination.namespace?)"
        )
    dep = items[0]
    ready = dep.get("status", {}).get("readyReplicas", 0)
    if not ready:
        not_passed(f"Deployment '{dep['metadata']['name']}' in namespace '{NS}' has no ready replicas")


@guarded
def main():
    require_cluster()
    _require_argocd_and_gitea()
    _check_seeded_repo_reachable()

    delete_ns(NS, wait=True)
    ensure_ns(NS)
    kubectl("delete", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False, timeout=60)

    try:
        _apply_application()
        app = _find_application()
        _check_application_spec(app)
        _trigger_sync(APP_NAME)
        _wait_synced_and_healthy(APP_NAME)
        _check_workload_in_namespace()

        passed(
            f"Application '{APP_NAME}' reached sync.status=Synced, health.status=Healthy, and its "
            f"chart landed a ready workload in namespace '{NS}'"
        )
    finally:
        kubectl("delete", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False, timeout=60)
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
