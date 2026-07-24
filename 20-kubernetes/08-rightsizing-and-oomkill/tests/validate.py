"""Validator for 20-kubernetes task 08 (rightsizing-and-oomkill).

Run from this task directory:

    uv run python tests/validate.py

Requires metrics-server already installed (given/install-metrics-server.sh).
Applies src/deployment.yaml into namespace t08 (recreated fresh), checks the
structural resource contract (requests+limits present for cpu/memory, both
policy caps respected), waits for the pod to become Ready (failing fast and
specifically if it gets OOMKilled instead), then drives a short burst of
/work load through a direct pod port-forward and asserts it survives with
zero restarts. Separately applies the given, fixed OOMKill fixture
(given/leak-pod.yaml) and asserts the container terminates with exitCode
137. Finally runs the NOTES.md doc-gate. Namespace t08 is deleted at the end
whether the task passes or fails.
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_keywords,
    check_sections,
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
)

NS = "t08"
SRC = TASK_ROOT / "src"
GIVEN = TASK_ROOT / "given"
NOTES = TASK_ROOT / "NOTES.md"

REQUIRED_ENV = {"MEM_MB": "180", "CPU_BURN_THREADS": "1"}
MAX_LIMITS_MEMORY_MI = 320
MAX_LIMITS_CPU_M = 1500


def _parse_cpu(v) -> int:
    """Millicores."""
    s = str(v)
    if s.endswith("m"):
        return int(s[:-1])
    return round(float(s) * 1000)


def _parse_mem(v) -> int:
    """Bytes."""
    s = str(v)
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "K": 1000, "M": 1000**2, "G": 1000**3}
    for suf, mult in units.items():
        if s.endswith(suf):
            return round(float(s[: -len(suf)]) * mult)
    return round(float(s))


def _require_metrics_server():
    result = kubectl("top", "nodes", check=False, timeout=20)
    if result.returncode != 0:
        not_passed(
            "`kubectl top nodes` failed -- metrics-server does not look installed/ready. "
            "Run `bash given/install-metrics-server.sh` first. "
            f"stderr: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else '(none)'}"
        )


def _apply(path: Path):
    result = kubectl("apply", "-f", str(path), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"kubectl apply -f {path.name} failed: {err}")


def _check_rightsize_deployment():
    dep = kubectl_json("get", "deployment", "rightsize-me", ns=NS, check=False)
    if not dep:
        not_passed(
            "Deployment 'rightsize-me' not found in namespace t08 after apply -- "
            "did you set metadata.name: rightsize-me? (stub applies nothing until filled in)"
        )

    spec = dep.get("spec", {})
    if spec.get("replicas") != 1:
        not_passed(f"Deployment 'rightsize-me' spec.replicas={spec.get('replicas')!r}, expected 1")

    pod_spec = spec.get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    if not containers:
        not_passed("Deployment 'rightsize-me' pod template has no containers")
    container = containers[0]

    if container.get("image") != "sandbox20-app:1.0":
        not_passed(f"container image={container.get('image')!r}, expected 'sandbox20-app:1.0'")
    if container.get("imagePullPolicy") != "IfNotPresent":
        not_passed(f"container imagePullPolicy={container.get('imagePullPolicy')!r}, expected 'IfNotPresent'")

    ports = container.get("ports", [])
    if not any(p.get("containerPort") == 8080 for p in ports):
        not_passed(f"container ports={ports!r}, expected containerPort 8080")

    env = {e.get("name"): e.get("value") for e in container.get("env", [])}
    for name, expected in REQUIRED_ENV.items():
        if env.get(name) != expected:
            not_passed(f"container env {name}={env.get(name)!r}, expected {expected!r}")

    resources = container.get("resources", {})
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    if "cpu" not in requests or "memory" not in requests:
        not_passed(f"resources.requests missing cpu/memory -- got {requests!r}")
    if "cpu" not in limits or "memory" not in limits:
        not_passed(f"resources.limits missing cpu/memory -- got {limits!r}")

    limits_mem_mi = _parse_mem(limits["memory"]) / (1024**2)
    if limits_mem_mi > MAX_LIMITS_MEMORY_MI:
        not_passed(
            f"limits.memory={limits['memory']!r} ({limits_mem_mi:.0f}Mi) exceeds the policy cap of "
            f"{MAX_LIMITS_MEMORY_MI}Mi -- this is over-provisioning, not right-sizing"
        )

    limits_cpu_m = _parse_cpu(limits["cpu"])
    if limits_cpu_m > MAX_LIMITS_CPU_M:
        not_passed(
            f"limits.cpu={limits['cpu']!r} ({limits_cpu_m}m) exceeds the policy cap of "
            f"{MAX_LIMITS_CPU_M}m -- this is over-provisioning, not right-sizing"
        )


def _rightsize_pod_name():
    data = kubectl_json("get", "pods", "-l", "app=rightsize-me", ns=NS, check=False)
    items = data.get("items", [])
    if not items:
        not_passed("no pod found with label app=rightsize-me in namespace t08")
    return items[0]["metadata"]["name"]


def _wait_rightsize_pod_ready(name: str, timeout: float = 90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pod = kubectl_json("get", "pod", name, ns=NS, check=False)
        status = pod.get("status", {})
        container_statuses = status.get("containerStatuses", [])
        if container_statuses:
            cs = container_statuses[0]
            terminated = cs.get("state", {}).get("terminated")
            if terminated:
                not_passed(
                    f"pod {name}: container terminated instead of becoming Ready "
                    f"(exitCode={terminated.get('exitCode')!r}, reason={terminated.get('reason')!r}) -- "
                    "if exitCode is 137, your memory limit is too low for what this workload actually needs"
                )
            if cs.get("restartCount", 0) > 0:
                not_passed(
                    f"pod {name}: container has restarted {cs['restartCount']} time(s) -- "
                    "check `kubectl describe pod` for the previous termination reason, likely OOMKilled"
                )
            if cs.get("ready"):
                return
        time.sleep(2)
    not_passed(f"pod {name} did not become Ready within {timeout}s")


def _drive_load_and_check_health(name: str):
    with port_forward(f"pod/{name}", 8080, NS) as local_port:
        for _ in range(15):
            status, body = http_get(f"http://127.0.0.1:{local_port}/work?ms=150", timeout=10)
            if status != 200:
                not_passed(f"GET /work?ms=150 through pod {name} returned status={status}, body={body!r}")

    pod = kubectl_json("get", "pod", name, ns=NS, check=False)
    status = pod.get("status", {})
    container_statuses = status.get("containerStatuses", [])
    if not container_statuses:
        not_passed(f"pod {name}: no containerStatuses after load run")
    cs = container_statuses[0]
    if cs.get("restartCount", 0) > 0:
        not_passed(f"pod {name}: container restarted during the load run (restartCount={cs['restartCount']})")
    if not cs.get("ready"):
        not_passed(f"pod {name}: container not ready after the load run -- state={cs.get('state')!r}")


def _check_leak_victim():
    _apply(GIVEN / "leak-pod.yaml")

    deadline = time.monotonic() + 120
    terminated = None
    while time.monotonic() < deadline:
        pod = kubectl_json("get", "pod", "leak-victim", ns=NS, check=False)
        status = pod.get("status", {})
        container_statuses = status.get("containerStatuses", [])
        if container_statuses:
            terminated = container_statuses[0].get("state", {}).get("terminated")
            if terminated:
                break
        time.sleep(2)

    if not terminated:
        not_passed("pod 'leak-victim' did not terminate within 120s -- expected it to be OOMKilled")

    if terminated.get("exitCode") != 137:
        not_passed(
            f"pod 'leak-victim' terminated with exitCode={terminated.get('exitCode')!r}, expected 137 "
            f"(reason={terminated.get('reason')!r})"
        )


REQUIRED_SECTIONS = [
    "Right-sizing observations",
    "OOMKill analysis",
    "Counterfactual: does a higher limit save it?",
    "QoS classification",
]

KEYWORDS = [
    "OOMKilled", "exit code", "137", "SIGKILL", "cgroup",
    "requests", "limits", "QoS", "Guaranteed", "Burstable",
    "BestEffort", "working set", "LEAK_MB_PER_S", "memory limit",
]


def _check_notes():
    sections = check_sections(NOTES, REQUIRED_SECTIONS, min_chars=300)
    full_text = "\n\n".join(sections.values())
    check_keywords(full_text, KEYWORDS, min_hits=9, label="NOTES.md")


@guarded
def main():
    require_cluster()
    _require_metrics_server()
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _apply(SRC / "deployment.yaml")
        _check_rightsize_deployment()
        name = _rightsize_pod_name()
        _wait_rightsize_pod_ready(name)
        _drive_load_and_check_health(name)

        _check_leak_victim()

        _check_notes()

        passed(
            f"'rightsize-me' pod {name} healthy under load with resources within policy caps; "
            "'leak-victim' OOMKilled as expected (exitCode 137); NOTES.md complete"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
