"""Validator for 20-kubernetes task 01 (deployment-service-config).

Run from this task directory:

    uv run python tests/validate.py

Applies everything in src/ into namespace t01 (recreated fresh), waits for
the Deployment rollout, then checks the running state behaviorally (ready
replica count, Service endpoint count, HTTP responses through a port-forward)
and via the pod spec (anti-cheat: env vars must be wired through
configMapKeyRef/secretKeyRef/fieldRef, not literal values). Namespace t01 is
deleted at the end whether the task passes or fails.
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    delete_ns,
    ensure_ns,
    guarded,
    http_get,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    port_forward,
    require_cluster,
    wait_rollout,
    wait_until,
)

NS = "t01"
SRC = TASK_ROOT / "src"

PLACEHOLDER_MARKERS = ("TODO(you)", "your choice", "<your")


def _apply_src():
    result = kubectl("apply", "-f", str(SRC), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f src/ failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _check_deployment():
    dep = kubectl_json("get", "deployment", "worker", ns=NS, check=False)
    if not dep:
        not_passed("Deployment 'worker' not found in namespace t01 after apply -- did you set metadata.name: worker?")

    spec = dep.get("spec", {})
    if spec.get("replicas") != 2:
        not_passed(f"Deployment 'worker' spec.replicas={spec.get('replicas')!r}, expected 2")

    wait_rollout("deployment/worker", NS, timeout=120)

    def _ready():
        d = kubectl_json("get", "deployment", "worker", ns=NS, check=False)
        return d.get("status", {}).get("readyReplicas", 0) == 2

    wait_until(_ready, timeout=60, interval=2, desc="Deployment 'worker' to reach 2 ready replicas")

    containers = spec.get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        not_passed("Deployment 'worker' pod template has no containers")
    container = containers[0]

    if container.get("image") != "sandbox20-app:1.0":
        not_passed(f"container image={container.get('image')!r}, expected 'sandbox20-app:1.0'")
    if container.get("imagePullPolicy") != "IfNotPresent":
        not_passed(
            f"container imagePullPolicy={container.get('imagePullPolicy')!r}, expected 'IfNotPresent' "
            "-- this image only exists inside kind's containerd, not a registry"
        )

    ports = container.get("ports", [])
    if not any(p.get("containerPort") == 8080 for p in ports):
        not_passed(f"container ports={ports!r}, expected containerPort 8080")

    return container


def _check_env_wiring(container):
    env = container.get("env", [])
    by_name = {e.get("name"): e for e in env}

    for required in ("CONFIG_GREETING", "APP_SECRET_TOKEN", "APP_POD_NAME", "REQUIRED_ENV"):
        if required not in by_name:
            not_passed(f"container env is missing '{required}'")

    cg = by_name["CONFIG_GREETING"]
    if "value" in cg or "valueFrom" not in cg or "configMapKeyRef" not in cg["valueFrom"]:
        not_passed(
            "CONFIG_GREETING must be wired via env[].valueFrom.configMapKeyRef, not a literal 'value' -- got "
            f"{cg!r}"
        )

    token = by_name["APP_SECRET_TOKEN"]
    if "value" in token or "valueFrom" not in token or "secretKeyRef" not in token["valueFrom"]:
        not_passed(
            "APP_SECRET_TOKEN must be wired via env[].valueFrom.secretKeyRef, not a literal 'value' -- got "
            f"{token!r}"
        )

    pod_name = by_name["APP_POD_NAME"]
    field_ref = pod_name.get("valueFrom", {}).get("fieldRef", {})
    if "value" in pod_name or field_ref.get("fieldPath") != "metadata.name":
        not_passed(
            "APP_POD_NAME must be wired via env[].valueFrom.fieldRef.fieldPath: metadata.name (downward API) "
            f"-- got {pod_name!r}"
        )

    req = by_name["REQUIRED_ENV"]
    req_value = req.get("value", "")
    names = {n.strip() for n in req_value.split(",") if n.strip()}
    if names != {"CONFIG_GREETING", "APP_SECRET_TOKEN"}:
        not_passed(
            f"REQUIRED_ENV={req_value!r}, expected exactly 'CONFIG_GREETING,APP_SECRET_TOKEN' (order-independent)"
        )


def _check_secret():
    secrets = kubectl_json("get", "secret", ns=NS)
    items = secrets.get("items", [])
    if not items:
        not_passed("no Secret found in namespace t01")
    non_default = [s for s in items if s.get("type") != "kubernetes.io/service-account-token"]
    if not non_default:
        not_passed("no non-service-account Secret found in namespace t01")
    if not any(s.get("type") == "Opaque" for s in non_default):
        types = [s.get("type") for s in non_default]
        not_passed(f"expected a Secret with type Opaque, found types: {types}")


def _check_service():
    svc = kubectl_json("get", "service", "worker", ns=NS, check=False)
    if not svc:
        not_passed("Service 'worker' not found in namespace t01 -- did you set metadata.name: worker?")

    spec = svc.get("spec", {})
    svc_type = spec.get("type", "ClusterIP")
    if svc_type != "ClusterIP":
        not_passed(f"Service 'worker' type={svc_type!r}, expected ClusterIP")

    ports = spec.get("ports", [])
    if not any(p.get("port") == 80 and p.get("targetPort") in (8080, "8080") for p in ports):
        not_passed(f"Service 'worker' ports={ports!r}, expected port 80 -> targetPort 8080")

    def _endpoints_ready():
        eps = kubectl_json("get", "endpoints", "worker", ns=NS, check=False)
        subsets = eps.get("subsets", [])
        count = sum(len(s.get("addresses", [])) for s in subsets)
        return count == 2

    wait_until(_endpoints_ready, timeout=60, interval=2, desc="Service 'worker' to have exactly 2 endpoints")


def _check_http():
    with port_forward("svc/worker", 80, NS) as local_port:
        status, body = http_get(f"http://127.0.0.1:{local_port}/")
        if status != 200:
            not_passed(f"GET / through the Service returned status={status}, body={body!r}")
        if '"app_version": "1.0"' not in body and '"app_version":"1.0"' not in body:
            not_passed(f"GET / did not report app_version 1.0: body={body!r}")

        status, body = http_get(f"http://127.0.0.1:{local_port}/env?name=CONFIG_GREETING")
        if status != 200:
            not_passed(f"GET /env?name=CONFIG_GREETING returned status={status}, body={body!r}")
        value = body.split("=", 1)[1].strip() if "=" in body else ""
        if not value:
            not_passed("GET /env?name=CONFIG_GREETING returned an empty value -- ConfigMap key value must be non-empty")
        if any(marker.lower() in value.lower() for marker in PLACEHOLDER_MARKERS):
            not_passed(f"CONFIG_GREETING value looks like an unfilled placeholder: {value!r}")

        status, body = http_get(f"http://127.0.0.1:{local_port}/env?name=APP_POD_NAME")
        if status != 200:
            not_passed(f"GET /env?name=APP_POD_NAME returned status={status}, body={body!r}")
        pod_name_value = body.split("=", 1)[1].strip() if "=" in body else ""
        pods = kubectl_json("get", "pods", "-l", "app=worker", ns=NS)
        actual_pod_names = {p["metadata"]["name"] for p in pods.get("items", [])}
        if pod_name_value not in actual_pod_names:
            not_passed(
                f"APP_POD_NAME echoed {pod_name_value!r} which is not one of the running pod names "
                f"{sorted(actual_pod_names)} -- downward API fieldRef looks wrong"
            )


@guarded
def main():
    require_cluster()
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _apply_src()
        container = _check_deployment()
        _check_env_wiring(container)
        _check_secret()
        _check_service()
        _check_http()
        passed("Deployment/Service/ConfigMap/Secret wired correctly: 2/2 ready replicas, 2 Service endpoints, "
               "app_version 1.0, CONFIG_GREETING/APP_SECRET_TOKEN/APP_POD_NAME sourced correctly")
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
