"""Validator for 20-kubernetes task 04 (first-chart-from-manifests).

Run from this task directory:

    uv run python tests/validate.py

Offline checks first (helm lint, helm template with various -f/--set
combinations, parsed as multi-doc YAML) so a learner gets a fast, precise
NOT PASSED before anything touches the cluster. Only once every structural
check passes does this install the chart live into namespace `t04`,
release name `t04-worker`, and check the same behavioral assertions task
01 checks against raw manifests. Namespace and release are torn down at
the end whether the live section passes or fails.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    CONTEXT,
    delete_ns,
    ensure_ns,
    guarded,
    http_get,
    kubectl_json,
    not_passed,
    passed,
    port_forward,
    require_cluster,
    wait_rollout,
)

CHART_DIR = TASK_ROOT / "chart"
RELEASE = "t04-worker"
NS = "t04"


def _last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line:
            return line
    return "(no output)"


def run_helm(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    cmd = ["helm", *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        not_passed("helm not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"helm {' '.join(args)} timed out after {timeout}s")


def helm_lint() -> None:
    result = run_helm("lint", str(CHART_DIR))
    if result.returncode != 0:
        not_passed(f"helm lint chart/ failed: {_last_line(result.stdout + result.stderr)}")


def helm_template(*extra_args: str, values_file=None) -> list[dict]:
    args = ["template", RELEASE, str(CHART_DIR)]
    if values_file is not None:
        args += ["-f", str(values_file)]
    args += list(extra_args)
    result = run_helm(*args)
    if result.returncode != 0:
        label = " ".join(extra_args) or (str(values_file) if values_file else "defaults")
        not_passed(f"helm template ({label}) failed: {_last_line(result.stdout + result.stderr)}")
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def by_kind(docs: list[dict]) -> dict:
    out: dict = {}
    for d in docs:
        out.setdefault(d.get("kind"), []).append(d)
    return out


def _deployment(docs: list[dict]) -> dict:
    dep = by_kind(docs).get("Deployment", [])
    if not dep:
        not_passed("no Deployment found in helm template output -- check chart/templates/deployment.yaml")
    return dep[0]


def _pod_annotations(dep: dict) -> dict:
    return dep.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {}) or {}


def _containers(dep: dict) -> list[dict]:
    return dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) or []


def _env_map(container: dict) -> dict:
    return {e["name"]: e for e in (container.get("env") or []) if "name" in e}


def _required_env_names(dep: dict):
    containers = _containers(dep)
    if not containers:
        return None
    entry = _env_map(containers[0]).get("REQUIRED_ENV")
    if entry is None or entry.get("value") is None:
        return None
    return {v.strip() for v in entry["value"].split(",") if v.strip()}


# --------------------------------------------------------------------------
# Structural checks (offline, no cluster mutation)
# --------------------------------------------------------------------------

def check_fullname_and_labels(docs: list[dict]) -> None:
    kinds = by_kind(docs)
    for kind in ("Deployment", "Service", "ConfigMap"):
        if kind not in kinds:
            not_passed(
                f"expected a {kind} in the bare-defaults render but found none -- "
                "chart/templates/ is still a stub for it"
            )
    for kind, items in kinds.items():
        for item in items:
            name = item.get("metadata", {}).get("name", "")
            if not name.startswith(RELEASE):
                not_passed(
                    f"{kind} named {name!r} is not named via the fullname helper "
                    f"(expected it to start with the release name {RELEASE!r})"
                )
            labels = item.get("metadata", {}).get("labels", {}) or {}
            missing = [
                k for k in ("app.kubernetes.io/name", "app.kubernetes.io/instance", "helm.sh/chart")
                if k not in labels
            ]
            if missing:
                not_passed(f"{kind} {name!r} is missing label(s) {missing} -- check the worker.labels helper")
            if labels.get("app.kubernetes.io/instance") != RELEASE:
                not_passed(
                    f"{kind} {name!r}: app.kubernetes.io/instance={labels.get('app.kubernetes.io/instance')!r}, "
                    f"expected {RELEASE!r}"
                )


def check_config_env_wiring(docs: list[dict]) -> None:
    dep = _deployment(docs)
    containers = _containers(dep)
    if not containers:
        not_passed("Deployment has no containers")
    env = _env_map(containers[0])
    cg = env.get("CONFIG_GREETING")
    if cg is None:
        not_passed("container env has no CONFIG_GREETING var")
    if not (cg.get("valueFrom") or {}).get("configMapKeyRef"):
        not_passed(f"CONFIG_GREETING is not wired via configMapKeyRef (got {cg!r})")

    names = _required_env_names(dep)
    if names is None:
        not_passed("Deployment container has no REQUIRED_ENV env var, or it has no literal value")
    if "CONFIG_GREETING" not in names:
        not_passed(f"REQUIRED_ENV={sorted(names)} does not include CONFIG_GREETING even though it's wired")


def check_checksum_annotation(base_docs: list[dict]) -> None:
    dep = _deployment(base_docs)
    checksum = _pod_annotations(dep).get("checksum/config")
    if not checksum:
        not_passed("Deployment pod template is missing a non-empty 'checksum/config' annotation")

    other_docs = helm_template("--set", "config.greeting=__validator_sentinel_value__")
    dep2 = _deployment(other_docs)
    checksum2 = _pod_annotations(dep2).get("checksum/config")
    if not checksum2:
        not_passed("checksum/config annotation disappeared when config.greeting changed")
    if checksum2 == checksum:
        not_passed(
            "checksum/config annotation did not change when config.greeting changed -- "
            "it must hash the rendered ConfigMap contents, not a fixed string"
        )


def check_replica_override() -> None:
    docs = helm_template("--set", "replicaCount=4")
    dep = _deployment(docs)
    replicas = dep.get("spec", {}).get("replicas")
    if replicas != 4:
        not_passed(
            f"--set replicaCount=4 rendered spec.replicas={replicas!r}, expected 4 -- "
            "wire replicaCount via .Values, don't hardcode it"
        )


def check_extra_env() -> None:
    docs = helm_template("--set", "extraEnv.APP_FOO=bar")
    dep = _deployment(docs)
    containers = _containers(dep)
    if not containers:
        not_passed("Deployment has no containers")
    entry = _env_map(containers[0]).get("APP_FOO")
    if entry is None or str(entry.get("value")) != "bar":
        not_passed(f"--set extraEnv.APP_FOO=bar did not render an APP_FOO=bar container env var (got {entry!r})")


def check_values_dev() -> list[dict]:
    dev_file = CHART_DIR / "values-dev.yaml"
    if not dev_file.exists():
        not_passed("chart/values-dev.yaml does not exist")
    docs = helm_template(values_file=dev_file)
    dep = _deployment(docs)
    replicas = dep.get("spec", {}).get("replicas")
    if replicas != 1:
        not_passed(f"-f chart/values-dev.yaml rendered spec.replicas={replicas!r}, expected 1")
    if "Secret" in by_kind(docs):
        not_passed("-f chart/values-dev.yaml rendered a Secret -- dev should have secret.enabled: false")
    names = _required_env_names(dep)
    if names is not None and "APP_SECRET_TOKEN" in names:
        not_passed(
            "dev render's REQUIRED_ENV lists APP_SECRET_TOKEN but secret.enabled is false in "
            "values-dev.yaml -- the app would crash on start (see app/app.py check_required_env)"
        )
    return docs


def check_values_prod() -> None:
    prod_file = CHART_DIR / "values-prod.yaml"
    if not prod_file.exists():
        not_passed("chart/values-prod.yaml does not exist")
    docs = helm_template(values_file=prod_file)
    dep = _deployment(docs)
    replicas = dep.get("spec", {}).get("replicas")
    if replicas != 3:
        not_passed(f"-f chart/values-prod.yaml rendered spec.replicas={replicas!r}, expected 3")

    containers = _containers(dep)
    if not containers:
        not_passed("Deployment has no containers")
    resources = containers[0].get("resources")
    if not resources:
        not_passed(
            "-f chart/values-prod.yaml rendered an empty/missing container 'resources' block -- "
            "prod values must set resources"
        )

    secrets = by_kind(docs).get("Secret", [])
    if not secrets:
        not_passed("-f chart/values-prod.yaml did not render a Secret -- prod should have secret.enabled: true")

    env = _env_map(containers[0])
    entry = env.get("APP_SECRET_TOKEN")
    if entry is None:
        not_passed("-f chart/values-prod.yaml: container env has no APP_SECRET_TOKEN")
    ref = (entry.get("valueFrom") or {}).get("secretKeyRef") or {}
    if not ref.get("name") or not ref.get("key"):
        not_passed(f"APP_SECRET_TOKEN is not wired via secretKeyRef (got {entry!r})")
    if not ref["name"].startswith(RELEASE):
        not_passed(f"Secret name {ref['name']!r} is not named via the fullname helper")

    names = _required_env_names(dep)
    if names is None or "APP_SECRET_TOKEN" not in names:
        not_passed(
            f"prod render's REQUIRED_ENV={sorted(names) if names else names} does not include "
            "APP_SECRET_TOKEN even though secret.enabled is true in values-prod.yaml"
        )


# --------------------------------------------------------------------------
# Live install/upgrade
# --------------------------------------------------------------------------

def live_verify(dev_docs: list[dict]) -> None:
    kinds = by_kind(dev_docs)
    dep = kinds["Deployment"][0]
    svc = kinds["Service"][0]

    dep_name = dep["metadata"]["name"]
    svc_name = svc["metadata"]["name"]
    svc_port = svc["spec"]["ports"][0]["port"]

    ensure_ns(NS)
    try:
        install = run_helm(
            "install", RELEASE, str(CHART_DIR),
            "-n", NS, "--create-namespace",
            "-f", str(CHART_DIR / "values-dev.yaml"),
            "--kube-context", CONTEXT,
            "--wait", "--timeout", "120s",
            timeout=150,
        )
        if install.returncode != 0:
            not_passed(f"helm install failed: {_last_line(install.stdout + install.stderr)}")

        wait_rollout(f"deployment/{dep_name}", NS, timeout=120)

        env_map = _env_map(_containers(dep)[0])
        cg = env_map.get("CONFIG_GREETING")
        ref = (cg.get("valueFrom") or {}).get("configMapKeyRef") if cg else None
        if not ref:
            not_passed("CONFIG_GREETING is not wired via configMapKeyRef in the dev render")
        cm_json = kubectl_json("get", "configmap", ref["name"], ns=NS)
        expected_greeting = (cm_json.get("data") or {}).get(ref["key"])
        if expected_greeting is None:
            not_passed(f"live ConfigMap {ref['name']!r} has no key {ref['key']!r} in namespace {NS}")

        with port_forward(f"svc/{svc_name}", svc_port, NS) as local_port:
            status, body = http_get(f"http://127.0.0.1:{local_port}/")
            if status != 200:
                not_passed(f"GET / through the Service returned {status}: {body}")

            status, body = http_get(f"http://127.0.0.1:{local_port}/env?name=CONFIG_GREETING")
            if status != 200:
                not_passed(f"GET /env?name=CONFIG_GREETING returned {status}: {body}")
            expected_line = f"CONFIG_GREETING={expected_greeting}"
            if body.strip() != expected_line:
                not_passed(
                    f"/env?name=CONFIG_GREETING returned {body.strip()!r}, expected it to echo "
                    f"the live ConfigMap's value ({expected_line!r})"
                )

        upgrade = run_helm(
            "upgrade", RELEASE, str(CHART_DIR),
            "-n", NS,
            "-f", str(CHART_DIR / "values-prod.yaml"),
            "--set", "secret.token=validator-live-token",
            "--kube-context", CONTEXT,
            "--wait", "--timeout", "120s",
            timeout=150,
        )
        if upgrade.returncode != 0:
            not_passed(f"helm upgrade failed: {_last_line(upgrade.stdout + upgrade.stderr)}")

        wait_rollout(f"deployment/{dep_name}", NS, timeout=120)

        dep_status = kubectl_json("get", "deployment", dep_name, ns=NS)
        ready = dep_status.get("status", {}).get("readyReplicas", 0)
        if ready != 3:
            not_passed(f"after upgrading to values-prod.yaml, deployment readyReplicas={ready}, expected 3")
    finally:
        try:
            run_helm("uninstall", RELEASE, "-n", NS, "--kube-context", CONTEXT, timeout=60)
        except SystemExit:
            pass
        delete_ns(NS, wait=False)


@guarded
def main() -> None:
    require_cluster()
    helm_lint()

    base_docs = helm_template()
    check_fullname_and_labels(base_docs)
    check_config_env_wiring(base_docs)
    check_checksum_annotation(base_docs)
    check_replica_override()
    check_extra_env()

    dev_docs = check_values_dev()
    check_values_prod()

    live_verify(dev_docs)

    passed(
        "helm lint clean; fullname/labels/checksum/replicaCount/extraEnv wiring verified via "
        f"helm template; values-dev/values-prod render correctly; live install+upgrade in ns {NS} "
        "succeeded with 3 ready replicas after the prod upgrade"
    )


if __name__ == "__main__":
    main()
