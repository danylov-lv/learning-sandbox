"""Validator for 20-kubernetes task 13 (ingress).

Run from this task directory:

    uv run python tests/validate.py

Checks ingress-nginx is installed (task 13 owns that install -- see
scripts/install.sh), seeds a healthy backend Deployment+Service into
namespace t13 (given/backend.yaml), applies the learner's src/ingress.yaml,
inspects the resulting Ingress object's spec (anti-cheat: host/backend/class
must be wired correctly, not just "some Ingress exists"), then curls
http://127.0.0.1:8320/ through the real kind host-port mapping with the
Host header the Ingress is supposed to route on and asserts it reaches the
backend app. A mismatched Host header must NOT reach the app (nginx's
default backend 404s it) -- proves the learner's rule actually gates on
Host rather than catching everything.

Namespace t13 is deleted at the end whether this passes or fails.
ingress-nginx itself is left installed -- this task owns it, later tasks
depend on it being there.
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
    require_cluster,
    wait_rollout,
    wait_until,
)

NS = "t13"
GIVEN = TASK_ROOT / "given" / "backend.yaml"
INGRESS_SRC = TASK_ROOT / "src" / "ingress.yaml"

INGRESS_NGINX_NS = "ingress-nginx"
INGRESS_NGINX_DEPLOYMENT = "ingress-nginx-controller"

HOST = "app.sandbox20.test"
WRONG_HOST = "not-this-app.sandbox20.test"
INGRESS_HTTP_PORT = 8320
BASE_URL = f"http://127.0.0.1:{INGRESS_HTTP_PORT}/"


def _check_ingress_nginx_installed():
    dep = kubectl_json("get", "deployment", INGRESS_NGINX_DEPLOYMENT, ns=INGRESS_NGINX_NS, check=False)
    if not dep:
        not_passed(
            "ingress-nginx is not installed (no Deployment "
            f"'{INGRESS_NGINX_DEPLOYMENT}' in namespace '{INGRESS_NGINX_NS}') -- "
            "run scripts/install.sh from this task directory first"
        )

    def _ready():
        d = kubectl_json("get", "deployment", INGRESS_NGINX_DEPLOYMENT, ns=INGRESS_NGINX_NS, check=False)
        return d.get("status", {}).get("readyReplicas", 0) >= 1

    wait_until(_ready, timeout=60, interval=2, desc="ingress-nginx controller to have a ready replica")

    ic = kubectl_json("get", "ingressclass", "nginx", check=False)
    if not ic:
        not_passed("IngressClass 'nginx' not found -- ingress-nginx install looks incomplete, run scripts/install.sh")


def _seed_backend():
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    result = kubectl("apply", "-f", str(GIVEN), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f given/backend.yaml failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")
    wait_rollout("deployment/backend", NS, timeout=120)


def _apply_ingress():
    result = kubectl("apply", "-f", str(INGRESS_SRC), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"kubectl apply -f src/ingress.yaml failed: {detail}")


def _check_ingress_spec():
    ing = kubectl_json("get", "ingress", "app", ns=NS, check=False)
    if not ing:
        not_passed("Ingress 'app' not found in namespace t13 after apply -- did you set metadata.name: app?")

    spec = ing.get("spec", {})
    if spec.get("ingressClassName") != "nginx":
        not_passed(f"Ingress 'app' spec.ingressClassName={spec.get('ingressClassName')!r}, expected 'nginx'")

    rules = spec.get("rules", [])
    matching = [r for r in rules if r.get("host") == HOST]
    if not matching:
        hosts = [r.get("host") for r in rules]
        not_passed(f"Ingress 'app' rules have host(s) {hosts!r}, expected a rule with host {HOST!r}")

    paths = matching[0].get("http", {}).get("paths", [])
    backend_ok = False
    for p in paths:
        svc = p.get("backend", {}).get("service", {})
        port = svc.get("port", {})
        if svc.get("name") == "backend" and (port.get("number") == 80 or str(port.get("number")) == "80"):
            backend_ok = True
            break
    if not backend_ok:
        not_passed(
            f"Ingress 'app' host {HOST!r} has no path backend pointing at service 'backend' port 80, "
            f"got paths={paths!r}"
        )


def _get(url: str, host: str, timeout: float = 5):
    try:
        resp = requests.get(url, headers={"Host": host}, timeout=timeout)
        return resp.status_code, resp.text
    except requests.RequestException as e:
        return None, str(e)


def _check_http_routing():
    def _reaches_app():
        status, body = _get(BASE_URL, HOST)
        return status is not None and 200 <= status < 300 and '"app_version"' in body

    wait_until(
        _reaches_app, timeout=60, interval=2,
        desc=f"http://127.0.0.1:{INGRESS_HTTP_PORT}/ with Host: {HOST} to reach the backend app",
    )

    status, body = _get(BASE_URL, HOST)
    if status is None or not (200 <= status < 300):
        not_passed(f"GET {BASE_URL} with Host: {HOST} returned status={status}, body={body!r}")
    if '"app_version"' not in body:
        not_passed(f"GET {BASE_URL} with Host: {HOST} didn't look like the backend app's response: {body!r}")

    wrong_status, wrong_body = _get(BASE_URL, WRONG_HOST)
    if wrong_status is not None and 200 <= wrong_status < 300 and '"app_version"' in wrong_body:
        not_passed(
            f"GET {BASE_URL} with Host: {WRONG_HOST} (a host not declared in the Ingress) also reached the "
            "backend app -- the Ingress rule must gate on Host, not accept every request"
        )


@guarded
def main():
    require_cluster()
    _check_ingress_nginx_installed()
    try:
        _seed_backend()
        _apply_ingress()
        _check_ingress_spec()
        _check_http_routing()
        passed(
            f"Ingress 'app' routes Host {HOST!r} -> Service backend:80, "
            f"verified via a real curl through http://127.0.0.1:{INGRESS_HTTP_PORT}/"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
