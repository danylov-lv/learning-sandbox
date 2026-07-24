"""Validator for 20-kubernetes task 05 (chart-advanced-deps-hooks-diffing).

Run from this task directory:

    uv run python tests/validate.py

Checks, in order (cheap/offline first, expensive/live last):

1. chart/Chart.yaml declares the queue-chart dependency with the right
   condition (first structural gate -- the stock chart fails here).
2. `helm dependency build` succeeds.
3. `helm template` renders the queue-chart's redis resources by default and
   renders none of them with `--set queue.enabled=false`.
4. The "queue-init" hook Job carries the required hook/weight/delete-policy
   annotations.
5. chart/values-dev.yaml and chart/values-prod.yaml exist and actually
   render differently; DIFF.md documents that session (doc-gated).
6. Live: install into namespace t05, prove the pre-install hook completed
   before the worker Deployment's pod was even created, prove redis and the
   worker pod are Ready, and prove the seeded queue actually drains through
   the running app (/metrics). Then uninstall and clean up.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    CONTEXT,
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
    wait_rollout,
    wait_until,
)

NS = "t05"
RELEASE = "t05-stack"
CHART = TASK_ROOT / "chart"
VALUES = CHART / "values.yaml"
DIFF_DOC = TASK_ROOT / "DIFF.md"

HOOK_JOB_NAME = "queue-init"


# --------------------------------------------------------------------------
# helm subprocess helpers
# --------------------------------------------------------------------------

def _last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line:
            return line
    return "(no error message)"


def _helm(*args: str, cwd: Path = CHART, timeout: int = 90) -> subprocess.CompletedProcess:
    cmd = ["helm", "--kube-context", CONTEXT] + list(args)
    try:
        return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        not_passed("helm not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"helm {' '.join(args)} timed out after {timeout}s")


def _helm_template(values_files=None, set_args=None) -> subprocess.CompletedProcess:
    cmd = ["template", RELEASE, "."]
    for vf in values_files or []:
        cmd += ["-f", str(vf)]
    for s in set_args or []:
        cmd += ["--set", s]
    return _helm(*cmd)


def _parse_manifests(rendered: str) -> list:
    docs = []
    for doc in yaml.safe_load_all(rendered):
        if doc:
            docs.append(doc)
    return docs


# --------------------------------------------------------------------------
# 1. Chart.yaml dependency + condition (first structural gate)
# --------------------------------------------------------------------------

def _check_dependency_declared():
    chart_yaml_path = CHART / "Chart.yaml"
    if not chart_yaml_path.exists():
        not_passed("chart/Chart.yaml not found")
    try:
        data = yaml.safe_load(chart_yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        not_passed(f"chart/Chart.yaml is not valid YAML: {e}")

    deps = data.get("dependencies") or []
    if not deps:
        not_passed(
            "chart/Chart.yaml has no entries under 'dependencies' -- add the queue-chart "
            "subchart dependency (see README.md 'What's required' step 1)"
        )

    match = next((d for d in deps if d.get("name") == "queue-chart"), None)
    if match is None:
        names = [d.get("name") for d in deps]
        not_passed(f"chart/Chart.yaml dependencies do not include an entry named 'queue-chart' (found: {names})")

    if match.get("condition") != "queue.enabled":
        not_passed(f"queue-chart dependency 'condition' is {match.get('condition')!r}, expected 'queue.enabled'")

    repo = str(match.get("repository", "")).replace("\\", "/")
    if "file://" not in repo or "given/queue-chart" not in repo:
        not_passed(
            f"queue-chart dependency 'repository' is {match.get('repository')!r}, expected a "
            "file:// path pointing at ../given/queue-chart"
        )


# --------------------------------------------------------------------------
# 2. helm dependency build
# --------------------------------------------------------------------------

def _dependency_build():
    result = _helm("dependency", "build")
    if result.returncode != 0:
        not_passed(f"helm dependency build failed: {_last_line(result.stderr or result.stdout)}")
    tgz = list((CHART / "charts").glob("queue-chart-*.tgz")) if (CHART / "charts").exists() else []
    if not tgz:
        not_passed("helm dependency build ran but chart/charts/queue-chart-*.tgz is missing")


# --------------------------------------------------------------------------
# 3. helm template conditional rendering
# --------------------------------------------------------------------------

def _mentions_redis(doc: dict) -> bool:
    """True iff `doc` is a resource that came from the queue-chart dependency
    -- checked by its label (not by string-searching the whole manifest,
    since the worker's own QUEUE_BACKEND=redis literal env var would give a
    false positive on that)."""
    labels = (doc.get("metadata", {}) or {}).get("labels", {}) or {}
    if labels.get("app.kubernetes.io/name") == "queue-chart":
        return True
    if doc.get("kind") == "Deployment":
        containers = (
            doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )
        for c in containers:
            image = str(c.get("image", ""))
            if image.startswith("redis:") or "/redis:" in image:
                return True
    return False


def _check_template_conditional():
    default_render = _helm_template(values_files=[VALUES])
    if default_render.returncode != 0:
        not_passed(f"helm template (default values) failed: {_last_line(default_render.stderr)}")
    default_docs = _parse_manifests(default_render.stdout)
    if not default_docs:
        not_passed("helm template (default values) rendered no manifests at all")
    if not any(_mentions_redis(d) for d in default_docs):
        not_passed(
            "default `helm template` render has no redis-backed resource from the queue-chart "
            "dependency -- check queue.enabled's default and the dependency condition"
        )

    disabled_render = _helm_template(values_files=[VALUES], set_args=["queue.enabled=false"])
    if disabled_render.returncode != 0:
        not_passed(f"helm template --set queue.enabled=false failed: {_last_line(disabled_render.stderr)}")
    disabled_docs = _parse_manifests(disabled_render.stdout)
    if any(_mentions_redis(d) for d in disabled_docs):
        not_passed(
            "`helm template --set queue.enabled=false` still rendered a queue-chart resource -- "
            "the dependency 'condition' isn't gating it"
        )

    return default_docs


# --------------------------------------------------------------------------
# 4. hook Job annotations
# --------------------------------------------------------------------------

def _check_hook_annotations(default_docs: list):
    job = next(
        (d for d in default_docs if d.get("kind") == "Job" and d.get("metadata", {}).get("name") == HOOK_JOB_NAME),
        None,
    )
    if job is None:
        not_passed(f"no rendered Job named '{HOOK_JOB_NAME}' found -- see README.md 'What's required' step 2")

    ann = job.get("metadata", {}).get("annotations") or {}

    hook = ann.get("helm.sh/hook", "")
    hook_parts = {p.strip() for p in hook.split(",") if p.strip()}
    if hook_parts != {"pre-install", "pre-upgrade"}:
        not_passed(f"'{HOOK_JOB_NAME}' Job helm.sh/hook={hook!r}, expected 'pre-install,pre-upgrade'")

    weight = ann.get("helm.sh/hook-weight")
    if weight is None:
        not_passed(f"'{HOOK_JOB_NAME}' Job is missing the helm.sh/hook-weight annotation")
    try:
        int(weight)
    except (TypeError, ValueError):
        not_passed(f"'{HOOK_JOB_NAME}' Job helm.sh/hook-weight={weight!r} is not an integer string")

    policy = ann.get("helm.sh/hook-delete-policy", "")
    policy_parts = {p.strip() for p in policy.split(",") if p.strip()}
    if policy_parts != {"before-hook-creation", "hook-succeeded"}:
        not_passed(
            f"'{HOOK_JOB_NAME}' Job helm.sh/hook-delete-policy={policy!r}, expected "
            "'before-hook-creation,hook-succeeded'"
        )


# --------------------------------------------------------------------------
# 5. diff workflow files + DIFF.md doc gate
# --------------------------------------------------------------------------

def _check_diff_values_and_doc():
    dev = CHART / "values-dev.yaml"
    prod = CHART / "values-prod.yaml"
    if not dev.exists():
        not_passed("chart/values-dev.yaml not found -- create it for the diff workflow (README.md step 3)")
    if not prod.exists():
        not_passed("chart/values-prod.yaml not found -- create it for the diff workflow (README.md step 3)")

    dev_render = _helm_template(values_files=[VALUES, dev])
    if dev_render.returncode != 0:
        not_passed(f"helm template -f values-dev.yaml failed: {_last_line(dev_render.stderr)}")
    prod_render = _helm_template(values_files=[VALUES, prod])
    if prod_render.returncode != 0:
        not_passed(f"helm template -f values-prod.yaml failed: {_last_line(prod_render.stderr)}")
    if dev_render.stdout.strip() == prod_render.stdout.strip():
        not_passed(
            "helm template renders identically for values-dev.yaml and values-prod.yaml -- "
            "they must actually differ (replicas, resources, QUEUE_KEY)"
        )

    sections = check_sections(
        DIFF_DOC,
        required=["Command", "Differences found", "Why each difference exists"],
        min_chars={"Command": 40, "Differences found": 150, "Why each difference exists": 150},
    )

    full_text = DIFF_DOC.read_text(encoding="utf-8")
    if "helm template" not in full_text:
        not_passed("DIFF.md must contain the literal command 'helm template' somewhere in it")

    check_keywords(
        sections["Differences found"],
        keywords=["replica", "resources", "cpu", "memory", "queue_key", "queue.key", "quantity"],
        min_hits=3,
        label="DIFF.md 'Differences found' section",
    )


# --------------------------------------------------------------------------
# 6. Live install / ordering / drain / uninstall
# --------------------------------------------------------------------------

def _events(ns: str) -> list:
    data = kubectl_json("get", "events", ns=ns, check=False)
    return data.get("items", [])


def _event_time(ev: dict):
    return ev.get("eventTime") or ev.get("lastTimestamp") or ev.get("firstTimestamp")


def _hook_completion_time_via_events(job_name: str, ns: str):
    """The hook Job is deleted (hook-delete-policy: hook-succeeded) almost
    immediately after it succeeds, often before helm install even returns --
    so we can't rely on reading it back with `kubectl get job`. Kubernetes
    Events aren't owned by the Job they describe, so they survive its
    deletion; use those instead."""
    best = None
    for ev in _events(ns):
        obj = ev.get("involvedObject", {})
        if obj.get("kind") != "Job" or obj.get("name") != job_name:
            continue
        if ev.get("reason") not in ("Completed",):
            continue
        t = _event_time(ev)
        if t and (best is None or t < best):
            best = t
    return best


def _hook_job_snapshot(ns: str, stop_flag: dict):
    """Best-effort: poll the hook Job directly in case it's still around
    long enough to read status.completionTime straight from the object."""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not stop_flag.get("stop"):
        data = kubectl_json("get", "job", HOOK_JOB_NAME, ns=ns, check=False)
        if data:
            completion_time = data.get("status", {}).get("completionTime")
            if completion_time:
                stop_flag["completion_time"] = completion_time
                return
        time.sleep(0.15)


def _helm_install():
    result = _helm(
        "install", RELEASE, ".",
        "-n", NS,
        "-f", str(VALUES),
        "--wait", "--timeout", "180s",
        timeout=200,
    )
    if result.returncode != 0:
        not_passed(f"helm install failed: {_last_line(result.stderr or result.stdout)}")


def _check_hook_ran_before_app_pod():
    import threading

    stop_flag = {"stop": False}
    poller = threading.Thread(target=_hook_job_snapshot, args=(NS, stop_flag), daemon=True)
    poller.start()

    _helm_install()

    stop_flag["stop"] = True
    poller.join(timeout=2)

    hook_time = stop_flag.get("completion_time") or _hook_completion_time_via_events(HOOK_JOB_NAME, NS)
    if not hook_time:
        not_passed(
            f"could not determine when the '{HOOK_JOB_NAME}' hook Job completed (no Job status snapshot "
            "and no 'Completed' Job event found) -- did the hook actually run and succeed?"
        )

    pods = kubectl_json("get", "pods", "-l", "app=worker", ns=NS)
    items = pods.get("items", [])
    if not items:
        not_passed("no pods found with label app=worker after helm install")
    pod_created = min(p["metadata"]["creationTimestamp"] for p in items)

    # Kubernetes timestamps here have only 1-second resolution, so use <=
    # rather than < -- the ordering is already structurally guaranteed by
    # Helm (a pre-install hook always completes before any non-hook
    # resource is created), this is a sanity check against that guarantee,
    # not a race we need to win by a strict margin.
    if not (hook_time <= pod_created):
        not_passed(
            f"'{HOOK_JOB_NAME}' hook completion time ({hook_time}) is not before/at the worker pod's "
            f"creationTimestamp ({pod_created}) -- the hook must finish before the app pod is even created"
        )


def _check_redis_ready():
    def _ready():
        pods = kubectl_json("get", "pods", "-l", "app.kubernetes.io/name=queue-chart", ns=NS, check=False)
        items = pods.get("items", [])
        if not items:
            return False
        for p in items:
            conditions = {c["type"]: c["status"] for c in p.get("status", {}).get("conditions", [])}
            if conditions.get("Ready") != "True":
                return False
        return True

    wait_until(_ready, timeout=90, interval=2, desc="the redis pod (queue-chart dependency) to be Ready")


def _check_worker_ready():
    wait_rollout("deployment/worker", NS, timeout=120)

    def _ready():
        dep = kubectl_json("get", "deployment", "worker", ns=NS, check=False)
        return dep.get("status", {}).get("readyReplicas", 0) >= 1

    wait_until(_ready, timeout=60, interval=2, desc="Deployment 'worker' to have at least 1 ready replica")


def _metric_value(text: str, name: str):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[0] == name:
            try:
                return float(parts[1])
            except ValueError:
                return None
    return None


def _check_queue_drained():
    with port_forward("svc/worker", 80, NS) as local_port:
        def _drained():
            status, body = http_get(f"http://127.0.0.1:{local_port}/metrics")
            if status != 200:
                return False
            processed = _metric_value(body, "app_processed_total")
            depth = _metric_value(body, "app_queue_depth")
            return processed is not None and processed > 0 and depth == 0

        wait_until(
            _drained, timeout=90, interval=2,
            desc="app_processed_total > 0 and app_queue_depth == 0 through /metrics (seeded queue draining)",
        )


def _helm_uninstall_and_check_hook_gone():
    result = _helm("uninstall", RELEASE, "-n", NS, timeout=120)
    if result.returncode != 0:
        not_passed(f"helm uninstall failed: {_last_line(result.stderr or result.stdout)}")

    job = kubectl_json("get", "job", HOOK_JOB_NAME, ns=NS, check=False)
    if job:
        not_passed(
            f"'{HOOK_JOB_NAME}' hook Job still present after helm uninstall -- expected it gone "
            "via hook-delete-policy: hook-succeeded"
        )


def _live_checks():
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _check_hook_ran_before_app_pod()
        _check_redis_ready()
        _check_worker_ready()
        _check_queue_drained()
        _helm_uninstall_and_check_hook_gone()
    finally:
        _helm("uninstall", RELEASE, "-n", NS, timeout=60)  # no-op if already uninstalled
        delete_ns(NS, wait=False)


@guarded
def main():
    require_cluster()

    _check_dependency_declared()
    _dependency_build()
    default_docs = _check_template_conditional()
    _check_hook_annotations(default_docs)
    _check_diff_values_and_doc()
    _live_checks()

    passed(
        "queue-chart dependency wired correctly, hook 'queue-init' ran and completed before the "
        "worker pod existed, redis + worker Ready, seeded queue drained to 0 via the running app, "
        "hook Job absent after uninstall, DIFF.md documents a real dev/prod render diff"
    )


if __name__ == "__main__":
    main()
