"""Validator for 20-kubernetes task 10 (crashloop-and-distroless).

Run from this task directory:

    uv run python tests/validate.py

Recreates namespace t10, applies given/broken.yaml (ingest CrashLoopBackOff,
render stuck NotReady, plus the standalone render-debug-target Pod), and
first confirms the fixture is actually broken the way the task claims
(non-vacuous check) before giving any credit. Applies src/ingest-fix.yaml
and src/render-fix.yaml on top, waits for both Deployments to become Ready,
and asserts:

  - ingest: REQUIRED_ENV is unchanged (the fix supplies the missing value,
    it doesn't weaken the check) and /env?name=CONFIG_QUEUE_URL echoes a
    real, non-empty value through the running pod.
  - render: still runs sandbox20-app:distroless (anti-cheat -- swapping to
    a shell-having image to dodge the ephemeral-container exercise is not
    a pass), still has a readinessProbe on /readyz, and the Service
    actually serves / and /readyz (proves the real port was fixed, however
    the learner chose to fix it).
  - render-debug-target: still runs sandbox20-app:distroless, and its
    spec.ephemeralContainers is non-empty -- proof an ephemeral debug
    container was actually attached to investigate it. This Pod is never
    replaced by the learner's fix (it isn't part of the render Deployment),
    so this is a stable, non-fragile place to look for that evidence,
    unlike the render Deployment's own pod which gets rolled the moment
    it's fixed.

Namespace t10 is deleted (best-effort, non-blocking) whether this passes or
fails.
"""

from __future__ import annotations

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

NS = "t10"
GIVEN_DIR = TASK_ROOT / "given"
SRC_DIR = TASK_ROOT / "src"
INGEST_FIX = SRC_DIR / "ingest-fix.yaml"
RENDER_FIX = SRC_DIR / "render-fix.yaml"

STUB_MARKERS = ("TODO(you)",)

EXPECTED_REQUIRED_ENV = "CONFIG_DB_URL,CONFIG_QUEUE_URL"


def _check_not_stub(path: Path):
    if not path.exists():
        not_passed(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip() or any(marker in text for marker in STUB_MARKERS):
        not_passed(f"{path} still looks like the unfilled TODO stub")


def _seed_fixture():
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    result = kubectl("apply", "-f", str(GIVEN_DIR / "broken.yaml"), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        not_passed(f"kubectl apply -f given/broken.yaml failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _container_state(pod: dict, name: str) -> dict:
    for cs in pod.get("status", {}).get("containerStatuses", []):
        if cs.get("name") == name:
            return cs
    return {}


def _pod_for(label_selector: str) -> dict:
    items = kubectl_json("get", "pods", "-l", label_selector, ns=NS).get("items", [])
    return items[0] if items else {}


def _verify_fixture_non_vacuous():
    def _ingest_crashlooping() -> bool:
        pod = _pod_for("app=ingest")
        if not pod:
            return False
        cs = _container_state(pod, "ingest")
        waiting = cs.get("state", {}).get("waiting", {})
        return waiting.get("reason") == "CrashLoopBackOff" or cs.get("restartCount", 0) >= 2

    wait_until(_ingest_crashlooping, timeout=120, interval=3, desc="ingest to reach CrashLoopBackOff")

    def _render_debug_target_running() -> bool:
        pod = kubectl_json("get", "pod", "render-debug-target", ns=NS, check=False)
        return pod.get("status", {}).get("phase") == "Running"

    wait_until(_render_debug_target_running, timeout=60, interval=2, desc="render-debug-target to be Running")

    render_dep = kubectl_json("get", "deployment", "render", ns=NS, check=False)
    ready = render_dep.get("status", {}).get("readyReplicas", 0)
    if ready:
        not_passed(
            f"render Deployment already shows readyReplicas={ready} before any fix was applied -- "
            "the broken fixture didn't reproduce the never-ready symptom, something is off"
        )


def _apply_fixes():
    for path in (INGEST_FIX, RENDER_FIX):
        result = kubectl("apply", "-f", str(path), ns=NS, check=False, timeout=60)
        if result.returncode != 0:
            not_passed(f"kubectl apply -f {path.name} failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()}")


def _check_ingest_fixed():
    wait_rollout("deployment/ingest", NS, timeout=120)

    dep = kubectl_json("get", "deployment", "ingest", ns=NS)
    containers = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        not_passed("ingest Deployment has no containers after applying the fix")
    env = {e.get("name"): e.get("value") for e in containers[0].get("env", []) if "name" in e}
    if env.get("REQUIRED_ENV") != EXPECTED_REQUIRED_ENV:
        not_passed(
            f"ingest container's REQUIRED_ENV changed to {env.get('REQUIRED_ENV')!r}, expected it to stay "
            f"{EXPECTED_REQUIRED_ENV!r} -- the fix is supplying CONFIG_QUEUE_URL, not weakening the check"
        )

    with port_forward("deployment/ingest", 8080, NS) as local_port:
        status, body = http_get(f"http://127.0.0.1:{local_port}/env?name=CONFIG_QUEUE_URL")
        if status != 200:
            not_passed(f"GET /env?name=CONFIG_QUEUE_URL on the ingest pod returned status={status}: {body!r}")
        value = body.strip().removeprefix("CONFIG_QUEUE_URL=")
        if not value:
            not_passed("ingest pod's CONFIG_QUEUE_URL is empty -- the missing value was never actually supplied")


def _check_render_fixed():
    wait_rollout("deployment/render", NS, timeout=120)

    dep = kubectl_json("get", "deployment", "render", ns=NS)
    containers = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        not_passed("render Deployment has no containers after applying the fix")
    c = containers[0]

    image = c.get("image", "")
    if not image.endswith("sandbox20-app:distroless"):
        not_passed(
            f"render container image is {image!r}, expected it to still be sandbox20-app:distroless -- "
            "swapping to a shell-having image dodges the ephemeral-container exercise and is not a pass"
        )

    readiness = c.get("readinessProbe", {})
    r_path = readiness.get("httpGet", {}).get("path")
    if r_path != "/readyz":
        not_passed(f"render container's readinessProbe must hit /readyz, found path={r_path!r}")

    with port_forward("svc/render", 80, NS) as local_port:
        status, body = http_get(f"http://127.0.0.1:{local_port}/readyz")
        if status != 200:
            not_passed(f"GET /readyz through svc/render returned status={status}: {body!r}")
        status, body = http_get(f"http://127.0.0.1:{local_port}/")
        if status != 200:
            not_passed(f"GET / through svc/render returned status={status}: {body!r}")


def _check_ephemeral_debug_evidence():
    pod = kubectl_json("get", "pod", "render-debug-target", ns=NS, check=False)
    if not pod:
        not_passed("render-debug-target Pod is gone -- it must stay in place as the ephemeral-debug target")

    image = pod.get("spec", {}).get("containers", [{}])[0].get("image", "")
    if not image.endswith("sandbox20-app:distroless"):
        not_passed(
            f"render-debug-target's container image is {image!r}, expected sandbox20-app:distroless -- "
            "don't replace this pod with one that has a shell, that defeats the exercise"
        )

    ephemeral = pod.get("spec", {}).get("ephemeralContainers", [])
    if not ephemeral:
        not_passed(
            "render-debug-target has no ephemeralContainers recorded -- you must actually run "
            "`kubectl debug -it render-debug-target --image=... --target=render` against it, "
            "not just read the YAML"
        )


@guarded
def main():
    require_cluster()
    try:
        _check_not_stub(INGEST_FIX)
        _check_not_stub(RENDER_FIX)

        _seed_fixture()
        _verify_fixture_non_vacuous()

        _apply_fixes()

        _check_ingest_fixed()
        _check_render_fixed()
        _check_ephemeral_debug_evidence()

        passed(
            "ingest fixed (CONFIG_QUEUE_URL supplied, REQUIRED_ENV intact), render fixed and still "
            "distroless, ephemeral debug container evidence found on render-debug-target"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
