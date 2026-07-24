"""Validator for 20-kubernetes task 17 (drift-selfheal-waves).

Run from this task directory:

    uv run python tests/validate.py

Requires Argo CD + Gitea already installed cluster-wide (task 16's
scripts/install.sh -- this task does NOT install or reinstall either).

What this does:

1. Parses the learner's src/manifests/*.yaml directly (anti-cheat: checks
   the required Deployment/Service/Job fields and annotations on the
   manifests themselves, not just "something synced").
2. Pushes those manifests into a fresh Gitea repo this task owns
   (sandbox20/t17-app.git -- distinct from task 16's platform-charts repo,
   never touches it) so Argo CD has a git source to sync from. The learner
   never needs Gitea write access for this.
3. Applies the learner's src/application.yaml into namespace argocd,
   checks its spec fields directly (repoURL/destination/syncPolicy), and
   waits (bounded) for Synced/Healthy.
4. Checks the Application's own sync-operation result for the PreSync
   hook Job's hookPhase (structural proof the hook actually ran and
   succeeded as part of the sync, before the main resources applied).
5. Mutates the live Deployment out-of-band (kubectl scale) and asserts
   (bounded wait) that Argo CD reverts it back to the desired replica
   count on its own -- this only happens if syncPolicy.automated.selfHeal
   is actually true, which is the non-vacuous part of the check.

The learner's Application is deleted from argocd and namespace t17 is
deleted at the end whether this passes or fails. The Gitea repo this
validator pushes to is left in place (force-pushed fresh on every run,
same idempotent convention as task 16's install script) -- Argo CD and
Gitea themselves are never touched.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

import requests  # noqa: E402
import yaml  # noqa: E402

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

NS = "t17"
ARGOCD_NS = "argocd"
APP_SRC = TASK_ROOT / "src" / "application.yaml"
MANIFESTS_DIR = TASK_ROOT / "src" / "manifests"
APP_NAME = "t17-app"

ARGOCD_SERVER_DEPLOYMENT = "argocd-server"
ARGOCD_REPO_SERVER_DEPLOYMENT = "argocd-repo-server"
ARGOCD_APP_CONTROLLER_STATEFULSET = "argocd-application-controller"
GITEA_DEPLOYMENT = "gitea"

# This task's own Gitea repo -- distinct from task 16's sandbox20/platform-charts,
# created (idempotently) and force-pushed to by this validator, never by the
# learner directly.
GITEA_ORG = "sandbox20"
GITEA_REPO = "t17-app"
GITEA_ADMIN_USER = "gitea-admin"
GITEA_ADMIN_PASSWORD = "sandbox20-gitea-admin-pw"

EXPECTED_REPO_HOST_FRAGMENT = "gitea-http.argocd.svc"
EXPECTED_REPO_PATH_FRAGMENT = f"{GITEA_ORG}/{GITEA_REPO}"
EXPECTED_DESTINATION_SERVER = "https://kubernetes.default.svc"
EXPECTED_DESTINATION_NS = NS

WORKLOAD_NAME = "t17-workload"
HOOK_JOB_NAME = "t17-preflight"
WORKLOAD_LABEL_SELECTOR = "app.kubernetes.io/name=t17-workload"

HOOK_ANNOTATION = "argocd.argoproj.io/hook"
HOOK_DELETE_POLICY_ANNOTATION = "argocd.argoproj.io/hook-delete-policy"
WAVE_ANNOTATION = "argocd.argoproj.io/sync-wave"
EXPECTED_HOOK_WAVE = "0"
EXPECTED_MAIN_WAVE = "1"
VALID_HOOK_TYPES = ("PreSync", "Sync")
VALID_DELETE_POLICIES = ("BeforeHookCreation", "HookSucceeded", "HookFailed")

SYNC_TIMEOUT_S = 300
SELFHEAL_TIMEOUT_S = 150
DRIFT_REPLICA_DELTA = 3


# --------------------------------------------------------------------------
# Preflight: cluster + Argo CD + Gitea already installed (task 16 owns this)
# --------------------------------------------------------------------------

def _require_argocd_and_gitea():
    for dep in (ARGOCD_SERVER_DEPLOYMENT, ARGOCD_REPO_SERVER_DEPLOYMENT):
        d = kubectl_json("get", "deployment", dep, ns=ARGOCD_NS, check=False)
        if not d:
            not_passed(
                f"Argo CD is not installed (no Deployment '{dep}' in namespace '{ARGOCD_NS}') -- "
                "run 16-argocd-app-by-hand/scripts/install.sh first"
            )
        if not d.get("status", {}).get("readyReplicas", 0):
            not_passed(f"Argo CD Deployment '{dep}' has no ready replicas -- run 16-argocd-app-by-hand/scripts/install.sh")

    sts = kubectl_json("get", "statefulset", ARGOCD_APP_CONTROLLER_STATEFULSET, ns=ARGOCD_NS, check=False)
    if not sts:
        not_passed(
            f"Argo CD is not installed (no StatefulSet '{ARGOCD_APP_CONTROLLER_STATEFULSET}' in "
            f"namespace '{ARGOCD_NS}') -- run 16-argocd-app-by-hand/scripts/install.sh first"
        )
    if not sts.get("status", {}).get("readyReplicas", 0):
        not_passed(
            f"Argo CD StatefulSet '{ARGOCD_APP_CONTROLLER_STATEFULSET}' has no ready replicas -- "
            "run 16-argocd-app-by-hand/scripts/install.sh"
        )

    gitea = kubectl_json("get", "deployment", GITEA_DEPLOYMENT, ns=ARGOCD_NS, check=False)
    if not gitea:
        not_passed(
            f"Gitea is not installed (no Deployment '{GITEA_DEPLOYMENT}' in namespace '{ARGOCD_NS}') -- "
            "run 16-argocd-app-by-hand/scripts/install.sh first"
        )
    if not gitea.get("status", {}).get("readyReplicas", 0):
        not_passed(f"Gitea Deployment '{GITEA_DEPLOYMENT}' has no ready replicas -- run 16-argocd-app-by-hand/scripts/install.sh")


# --------------------------------------------------------------------------
# Parse + validate the learner's src/manifests/*.yaml directly
# --------------------------------------------------------------------------

def _load_manifest_files() -> list[Path]:
    if not MANIFESTS_DIR.is_dir():
        not_passed(f"expected directory not found: {MANIFESTS_DIR}")
    files = sorted(MANIFESTS_DIR.glob("*.yaml")) + sorted(MANIFESTS_DIR.glob("*.yml"))
    if not files:
        not_passed(f"no *.yaml files found under {MANIFESTS_DIR} -- write the Deployment/Service/hook Job there")
    return files


def _load_docs(files: list[Path]) -> list[dict]:
    docs = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        try:
            for doc in yaml.safe_load_all(text):
                if doc:
                    docs.append(doc)
        except yaml.YAMLError as e:
            not_passed(f"{f.relative_to(TASK_ROOT)} is not valid YAML: {e}")
    return docs


def _find_one(docs: list[dict], kind: str, name: str) -> dict:
    matches = [
        d for d in docs
        if d.get("kind") == kind and d.get("metadata", {}).get("name") == name
    ]
    if not matches:
        not_passed(
            f"no {kind} named '{name}' found in src/manifests/*.yaml -- "
            "src/manifests/ only contains TODO comment stubs until you replace them with real resources"
            if len(docs) == 0 else
            f"no {kind} named '{name}' found in src/manifests/*.yaml -- see README.md for the exact "
            "name/kind contract each resource must use"
        )
    return matches[0]


def _validate_deployment_doc(dep: dict) -> int:
    annotations = dep.get("metadata", {}).get("annotations") or {}
    wave = annotations.get(WAVE_ANNOTATION)
    if wave != EXPECTED_MAIN_WAVE:
        not_passed(
            f"Deployment '{WORKLOAD_NAME}' metadata.annotations['{WAVE_ANNOTATION}']={wave!r}, "
            f"expected {EXPECTED_MAIN_WAVE!r} (it must sync after the hook Job's wave {EXPECTED_HOOK_WAVE!r})"
        )

    labels = dep.get("metadata", {}).get("labels") or {}
    if labels.get("app.kubernetes.io/name") != "t17-workload":
        not_passed(f"Deployment '{WORKLOAD_NAME}' is missing label app.kubernetes.io/name=t17-workload")

    replicas = dep.get("spec", {}).get("replicas")
    if not isinstance(replicas, int) or replicas < 1:
        not_passed(f"Deployment '{WORKLOAD_NAME}' spec.replicas={replicas!r}, expected a positive integer")

    containers = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or []
    if not containers or not any("sandbox20-app" in (c.get("image") or "") for c in containers):
        not_passed(f"Deployment '{WORKLOAD_NAME}' has no container using the sandbox20-app image")

    return replicas


def _validate_service_doc(svc: dict):
    annotations = svc.get("metadata", {}).get("annotations") or {}
    wave = annotations.get(WAVE_ANNOTATION)
    if wave != EXPECTED_MAIN_WAVE:
        not_passed(
            f"Service '{WORKLOAD_NAME}' metadata.annotations['{WAVE_ANNOTATION}']={wave!r}, "
            f"expected {EXPECTED_MAIN_WAVE!r}"
        )
    selector = svc.get("spec", {}).get("selector") or {}
    if selector.get("app.kubernetes.io/name") != "t17-workload":
        not_passed(f"Service '{WORKLOAD_NAME}' spec.selector does not select app.kubernetes.io/name=t17-workload")


def _validate_hook_job_doc(job: dict):
    annotations = job.get("metadata", {}).get("annotations") or {}

    hook = annotations.get(HOOK_ANNOTATION)
    if hook not in VALID_HOOK_TYPES:
        not_passed(
            f"Job '{HOOK_JOB_NAME}' metadata.annotations['{HOOK_ANNOTATION}']={hook!r}, "
            f"expected one of {VALID_HOOK_TYPES}"
        )

    delete_policy = annotations.get(HOOK_DELETE_POLICY_ANNOTATION)
    if delete_policy not in VALID_DELETE_POLICIES:
        not_passed(
            f"Job '{HOOK_JOB_NAME}' metadata.annotations['{HOOK_DELETE_POLICY_ANNOTATION}']={delete_policy!r}, "
            f"expected one of {VALID_DELETE_POLICIES} (without this, a re-sync -- including a "
            "self-heal-triggered one -- fails trying to create a Job whose name already exists)"
        )

    wave = annotations.get(WAVE_ANNOTATION)
    if wave != EXPECTED_HOOK_WAVE:
        not_passed(
            f"Job '{HOOK_JOB_NAME}' metadata.annotations['{WAVE_ANNOTATION}']={wave!r}, "
            f"expected {EXPECTED_HOOK_WAVE!r} (it must sync before the main workload's wave {EXPECTED_MAIN_WAVE!r})"
        )

    restart_policy = job.get("spec", {}).get("template", {}).get("spec", {}).get("restartPolicy")
    if restart_policy not in ("Never", "OnFailure"):
        not_passed(f"Job '{HOOK_JOB_NAME}' spec.template.spec.restartPolicy={restart_policy!r}, expected Never or OnFailure")


def _validate_manifests() -> int:
    """Returns the learner's chosen replica count (needed later for the drift check)."""
    files = _load_manifest_files()
    docs = _load_docs(files)

    dep = _find_one(docs, "Deployment", WORKLOAD_NAME)
    svc = _find_one(docs, "Service", WORKLOAD_NAME)
    job = _find_one(docs, "Job", HOOK_JOB_NAME)

    replicas = _validate_deployment_doc(dep)
    _validate_service_doc(svc)
    _validate_hook_job_doc(job)
    return replicas


# --------------------------------------------------------------------------
# Push the learner's manifests into this task's own Gitea repo
# --------------------------------------------------------------------------

def _ensure_repo(base_url: str, auth: tuple[str, str]):
    resp = requests.get(f"{base_url}/api/v1/repos/{GITEA_ORG}/{GITEA_REPO}", auth=auth, timeout=10)
    if resp.status_code == 200:
        return
    if resp.status_code != 404:
        not_passed(f"unexpected Gitea response checking repo {GITEA_ORG}/{GITEA_REPO}: {resp.status_code} {resp.text}")
    create = requests.post(
        f"{base_url}/api/v1/orgs/{GITEA_ORG}/repos",
        auth=auth,
        json={"name": GITEA_REPO, "private": False, "auto_init": False},
        timeout=10,
    )
    if create.status_code not in (201, 200):
        not_passed(f"failed to create Gitea repo {GITEA_ORG}/{GITEA_REPO}: {create.status_code} {create.text}")


def _git(args: list[str], cwd: Path):
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        not_passed(f"git {' '.join(args)} failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")
    return result


def _push_manifests(local_port: int):
    base_url = f"http://127.0.0.1:{local_port}"
    auth = (GITEA_ADMIN_USER, GITEA_ADMIN_PASSWORD)
    _ensure_repo(base_url, auth)

    workdir = Path(tempfile.mkdtemp(prefix="t17-gitea-"))
    try:
        for f in _load_manifest_files():
            shutil.copy2(f, workdir / f.name)
        _git(["init", "-q", "-b", "main"], workdir)
        _git(["add", "-A"], workdir)
        _git(["-c", "user.email=validator@sandbox20.test", "-c", "user.name=t17 validator", "commit", "-q", "-m", "seed: t17 manifests"], workdir)
        push_url = f"http://{GITEA_ADMIN_USER}:{GITEA_ADMIN_PASSWORD}@127.0.0.1:{local_port}/{GITEA_ORG}/{GITEA_REPO}.git"
        _git(["push", "-q", "-f", push_url, "main:main"], workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _seed_gitea_repo():
    with port_forward(f"svc/{GITEA_DEPLOYMENT}-http", 3000, ARGOCD_NS) as local_port:
        _push_manifests(local_port)


# --------------------------------------------------------------------------
# Apply + check the learner's Application
# --------------------------------------------------------------------------

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
            f"src/application.yaml -- did you set metadata.name: {APP_NAME} and metadata.namespace: {ARGOCD_NS}?"
        )
    return app


def _check_application_spec(app: dict) -> str:
    name = app.get("metadata", {}).get("name")
    spec = app.get("spec", {})

    source = spec.get("source") or (spec.get("sources") or [{}])[0]
    repo_url = source.get("repoURL", "")
    if EXPECTED_REPO_HOST_FRAGMENT not in repo_url or EXPECTED_REPO_PATH_FRAGMENT not in repo_url:
        not_passed(
            f"Application '{name}' spec.source.repoURL={repo_url!r} does not point at this task's Gitea "
            f"repo (expected it to contain both {EXPECTED_REPO_HOST_FRAGMENT!r} and {EXPECTED_REPO_PATH_FRAGMENT!r})"
        )

    path = source.get("path", "")
    if path not in (".", "", None):
        not_passed(f"Application '{name}' spec.source.path={path!r}, expected '.' -- manifests are pushed to the repo root")

    destination = spec.get("destination", {})
    dest_server = destination.get("server", "")
    dest_name = destination.get("name", "")
    if dest_server != EXPECTED_DESTINATION_SERVER and dest_name not in ("in-cluster",):
        not_passed(
            f"Application '{name}' spec.destination.server={dest_server!r}, expected {EXPECTED_DESTINATION_SERVER!r}"
        )
    if destination.get("namespace") != EXPECTED_DESTINATION_NS:
        not_passed(
            f"Application '{name}' spec.destination.namespace={destination.get('namespace')!r}, expected {EXPECTED_DESTINATION_NS!r}"
        )

    sync_policy = spec.get("syncPolicy") or {}
    automated = sync_policy.get("automated")
    if not automated:
        not_passed(
            f"Application '{name}' has no spec.syncPolicy.automated -- this task requires an automated "
            "syncPolicy (a manual-sync Application can't be tested for self-heal at all, since drift would "
            "just sit there OutOfSync until someone runs a manual sync)"
        )
    if automated.get("selfHeal") is not True:
        not_passed(
            f"Application '{name}' spec.syncPolicy.automated.selfHeal={automated.get('selfHeal')!r}, expected true "
            "-- this is the whole point of this task's drift check"
        )
    if automated.get("prune") is not True:
        not_passed(f"Application '{name}' spec.syncPolicy.automated.prune={automated.get('prune')!r}, expected true")

    return name


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
        sync_status = status.get("sync", {}).get("status")
        health_status = status.get("health", {}).get("status")
        return sync_status == "Synced" and health_status == "Healthy"

    wait_until(
        _check, timeout=SYNC_TIMEOUT_S, interval=5,
        desc=f"Application '{name}' to reach sync.status=Synced and health.status=Healthy",
    )


# --------------------------------------------------------------------------
# Structural checks against the live cluster + Argo's own sync result
# --------------------------------------------------------------------------

def _check_workload_landed():
    dep = kubectl_json("get", "deployment", WORKLOAD_NAME, ns=NS, check=False)
    if not dep:
        not_passed(
            f"no Deployment '{WORKLOAD_NAME}' found in namespace '{NS}' -- the Application reports "
            "Synced/Healthy but the workload didn't actually land there"
        )
    if not dep.get("status", {}).get("readyReplicas", 0):
        not_passed(f"Deployment '{WORKLOAD_NAME}' in namespace '{NS}' has no ready replicas")

    svc = kubectl_json("get", "service", WORKLOAD_NAME, ns=NS, check=False)
    if not svc:
        not_passed(f"no Service '{WORKLOAD_NAME}' found in namespace '{NS}'")


def _check_hook_ordering(name: str):
    """Structural proof the PreSync hook actually ran (and succeeded) as
    part of the sync -- read from the Application's own operationState,
    which records this regardless of whether the Job itself was later
    deleted by a hook-delete-policy."""
    app = kubectl_json("get", "application.argoproj.io", name, ns=ARGOCD_NS, check=False)
    resources = (app.get("status", {}) or {}).get("operationState", {}).get("syncResult", {}).get("resources") or []
    hook_entries = [
        r for r in resources
        if r.get("kind") == "Job" and r.get("name") == HOOK_JOB_NAME and r.get("hookType")
    ]
    if not hook_entries:
        not_passed(
            f"Application '{name}' status.operationState.syncResult.resources has no hook entry for "
            f"Job '{HOOK_JOB_NAME}' -- expected argocd.argoproj.io/hook to make it a hook resource of the sync"
        )
    hook_entry = hook_entries[0]
    if hook_entry.get("hookPhase") != "Succeeded":
        not_passed(
            f"PreSync hook Job '{HOOK_JOB_NAME}' hookPhase={hook_entry.get('hookPhase')!r}, expected 'Succeeded' "
            f"(message: {hook_entry.get('message', '')!r})"
        )

    # Best-effort: if the Job is still around (learner used BeforeHookCreation,
    # not HookSucceeded), confirm it actually completed before the workload's
    # pods were created -- a concrete, non-wall-clock ordering signal.
    job = kubectl_json("get", "job", HOOK_JOB_NAME, ns=NS, check=False)
    if job:
        completion_time = job.get("status", {}).get("completionTime")
        pods = kubectl_json("get", "pods", "-l", WORKLOAD_LABEL_SELECTOR, ns=NS, check=False)
        pod_times = [
            p["metadata"]["creationTimestamp"]
            for p in pods.get("items", [])
            if p.get("metadata", {}).get("creationTimestamp")
        ]
        if completion_time and pod_times:
            def _parse(ts):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if _parse(completion_time) > min(_parse(t) for t in pod_times):
                not_passed(
                    f"hook Job '{HOOK_JOB_NAME}' completed at {completion_time}, which is AFTER the "
                    f"earliest workload pod was created -- the PreSync hook did not actually run before "
                    "the main workload"
                )


def _check_drift_selfheal(orig_replicas: int):
    drift_replicas = orig_replicas + DRIFT_REPLICA_DELTA

    kubectl("scale", f"deployment/{WORKLOAD_NAME}", f"--replicas={drift_replicas}", ns=NS, check=False, timeout=30)

    def _drift_landed():
        dep = kubectl_json("get", "deployment", WORKLOAD_NAME, ns=NS, check=False)
        return dep.get("spec", {}).get("replicas") == drift_replicas

    wait_until(
        _drift_landed, timeout=20, interval=1,
        desc=f"the out-of-band 'kubectl scale --replicas={drift_replicas}' mutation to actually land first",
    )

    def _reverted():
        dep = kubectl_json("get", "deployment", WORKLOAD_NAME, ns=NS, check=False)
        return dep.get("spec", {}).get("replicas") == orig_replicas

    wait_until(
        _reverted, timeout=SELFHEAL_TIMEOUT_S, interval=3,
        desc=(
            f"Argo CD to self-heal deployment/{WORKLOAD_NAME} back to {orig_replicas} replicas after an "
            f"out-of-band scale to {drift_replicas} (requires spec.syncPolicy.automated.selfHeal: true "
            "in src/application.yaml -- a manual or non-selfHeal Application would leave this drifted "
            "and OutOfSync forever)"
        ),
    )


@guarded
def main():
    require_cluster()
    _require_argocd_and_gitea()

    orig_replicas = _validate_manifests()
    _seed_gitea_repo()

    delete_ns(NS, wait=True)
    ensure_ns(NS)
    kubectl("delete", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False, timeout=60)

    try:
        _apply_application()
        app = _find_application()
        _check_application_spec(app)
        _trigger_sync(APP_NAME)
        _wait_synced_and_healthy(APP_NAME)
        _check_workload_landed()
        _check_hook_ordering(APP_NAME)
        _check_drift_selfheal(orig_replicas)

        passed(
            f"Application '{APP_NAME}' synced with correct wave/hook ordering, and self-healed an "
            f"out-of-band drift back to {orig_replicas} replicas"
        )
    finally:
        kubectl("delete", "application.argoproj.io", APP_NAME, ns=ARGOCD_NS, check=False, timeout=60)
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
