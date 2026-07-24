"""Validator for 20-kubernetes task 03 (jobs-cronjobs-and-resources).

Run from this task directory:

    uv run python tests/validate.py

Applies src/job.yaml into namespace t03 (recreated fresh), waits for the
Job to reach status.succeeded == 4, checks the Job's own spec fields, and
proves parallelism actually happened (two finished pods whose running
intervals overlap) rather than trusting the spec field on paper. Checks
every job pod's resources (requests + limits, exactly as contracted) and
resulting QoS class. Then applies src/cronjob.yaml, checks its structural
fields, waits for its first spawned Job to appear and complete, suspends
it, and re-checks the history-limit fields. Namespace t03 is deleted at
the end whether the task passes or fails.
"""

import sys
from datetime import datetime
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    delete_ns,
    ensure_ns,
    guarded,
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    require_cluster,
    wait_until,
)

NS = "t03"
SRC = TASK_ROOT / "src"

EXPECTED_REQUESTS = {"cpu": "50m", "memory": "64Mi"}
EXPECTED_LIMITS = {"cpu": "200m", "memory": "128Mi"}


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


def _apply(path: Path):
    result = kubectl("apply", "-f", str(path), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"kubectl apply -f {path.name} failed: {err}")


def _check_resources(resources: dict, label: str):
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    if "cpu" not in requests or "memory" not in requests:
        not_passed(f"{label}: resources.requests missing cpu/memory -- got {requests!r}")
    if "cpu" not in limits or "memory" not in limits:
        not_passed(f"{label}: resources.limits missing cpu/memory -- got {limits!r}")

    if _parse_cpu(requests["cpu"]) != _parse_cpu(EXPECTED_REQUESTS["cpu"]):
        not_passed(f"{label}: requests.cpu={requests['cpu']!r}, expected {EXPECTED_REQUESTS['cpu']!r}")
    if _parse_mem(requests["memory"]) != _parse_mem(EXPECTED_REQUESTS["memory"]):
        not_passed(f"{label}: requests.memory={requests['memory']!r}, expected {EXPECTED_REQUESTS['memory']!r}")
    if _parse_cpu(limits["cpu"]) != _parse_cpu(EXPECTED_LIMITS["cpu"]):
        not_passed(f"{label}: limits.cpu={limits['cpu']!r}, expected {EXPECTED_LIMITS['cpu']!r}")
    if _parse_mem(limits["memory"]) != _parse_mem(EXPECTED_LIMITS["memory"]):
        not_passed(f"{label}: limits.memory={limits['memory']!r}, expected {EXPECTED_LIMITS['memory']!r}")


def _check_job_spec():
    job = kubectl_json("get", "job", "rescrape", ns=NS, check=False)
    if not job:
        not_passed("Job 'rescrape' not found in namespace t03 after apply -- did you set metadata.name: rescrape?")

    spec = job.get("spec", {})
    if spec.get("completions") != 4:
        not_passed(f"Job 'rescrape' spec.completions={spec.get('completions')!r}, expected 4")
    if spec.get("parallelism") != 2:
        not_passed(f"Job 'rescrape' spec.parallelism={spec.get('parallelism')!r}, expected 2")
    if spec.get("backoffLimit") != 2:
        not_passed(f"Job 'rescrape' spec.backoffLimit={spec.get('backoffLimit')!r}, expected 2")

    pod_spec = spec.get("template", {}).get("spec", {})
    if pod_spec.get("restartPolicy") != "Never":
        not_passed(f"Job 'rescrape' pod restartPolicy={pod_spec.get('restartPolicy')!r}, expected 'Never'")

    containers = pod_spec.get("containers", [])
    if not containers:
        not_passed("Job 'rescrape' pod template has no containers")
    container = containers[0]
    if container.get("image") != "sandbox20-app:1.0":
        not_passed(f"Job 'rescrape' container image={container.get('image')!r}, expected 'sandbox20-app:1.0'")

    _check_resources(container.get("resources", {}), "Job 'rescrape' container")


def _wait_job_complete():
    def _done():
        job = kubectl_json("get", "job", "rescrape", ns=NS, check=False)
        return job.get("status", {}).get("succeeded", 0) == 4

    wait_until(_done, timeout=180, interval=3, desc="Job 'rescrape' to reach status.succeeded == 4")


def _job_pods():
    data = kubectl_json("get", "pods", "-l", "job-name=rescrape", ns=NS)
    return data.get("items", [])


def _parse_ts(ts: str):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def _check_overlap_and_qos(pods):
    if len(pods) != 4:
        not_passed(f"expected 4 pods with label job-name=rescrape, found {len(pods)}")

    intervals = []
    for pod in pods:
        name = pod["metadata"]["name"]
        status = pod.get("status", {})
        start_raw = status.get("startTime")
        if not start_raw:
            not_passed(f"pod {name}: status.startTime missing")

        container_statuses = status.get("containerStatuses", [])
        if not container_statuses:
            not_passed(f"pod {name}: no containerStatuses")
        terminated = container_statuses[0].get("state", {}).get("terminated")
        if not terminated or not terminated.get("finishedAt"):
            not_passed(f"pod {name}: container not terminated with a finishedAt timestamp -- got {container_statuses[0].get('state')!r}")

        start = _parse_ts(start_raw)
        finish = _parse_ts(terminated["finishedAt"])
        intervals.append((name, start, finish))

        if status.get("qosClass") != "Burstable":
            not_passed(f"pod {name}: status.qosClass={status.get('qosClass')!r}, expected 'Burstable'")

        _check_resources(pod["spec"]["containers"][0].get("resources", {}), f"pod {name} container")

    overlap_found = False
    overlap_detail = None
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            n1, s1, f1 = intervals[i]
            n2, s2, f2 = intervals[j]
            latest_start = max(s1, s2)
            earliest_finish = min(f1, f2)
            if latest_start < earliest_finish:
                overlap_found = True
                overlap_detail = (n1, n2, latest_start, earliest_finish)
                break
        if overlap_found:
            break

    if not overlap_found:
        detail = ", ".join(f"{n}=[{s.isoformat()}, {f.isoformat()}]" for n, s, f in intervals)
        not_passed(
            "no two pods' [startTime, finishedAt] intervals overlap -- parallelism: 2 does not appear to have "
            f"run any two shards concurrently. Pod intervals: {detail}"
        )

    return overlap_detail


def _check_cronjob_spec():
    cj = kubectl_json("get", "cronjob", "scheduled-scrape", ns=NS, check=False)
    if not cj:
        not_passed(
            "CronJob 'scheduled-scrape' not found in namespace t03 after apply -- "
            "did you set metadata.name: scheduled-scrape?"
        )

    spec = cj.get("spec", {})
    if spec.get("schedule") != "* * * * *":
        not_passed(f"CronJob spec.schedule={spec.get('schedule')!r}, expected '* * * * *'")
    if spec.get("concurrencyPolicy") != "Forbid":
        not_passed(f"CronJob spec.concurrencyPolicy={spec.get('concurrencyPolicy')!r}, expected 'Forbid'")
    if spec.get("successfulJobsHistoryLimit") != 2:
        not_passed(f"CronJob spec.successfulJobsHistoryLimit={spec.get('successfulJobsHistoryLimit')!r}, expected 2")
    if spec.get("failedJobsHistoryLimit") != 1:
        not_passed(f"CronJob spec.failedJobsHistoryLimit={spec.get('failedJobsHistoryLimit')!r}, expected 1")
    if spec.get("startingDeadlineSeconds") in (None, 0):
        not_passed(
            f"CronJob spec.startingDeadlineSeconds={spec.get('startingDeadlineSeconds')!r}, "
            "expected a positive value to be set"
        )

    job_spec = spec.get("jobTemplate", {}).get("spec", {})
    if job_spec.get("completions") != 1:
        not_passed(f"CronJob jobTemplate spec.completions={job_spec.get('completions')!r}, expected 1")

    pod_spec = job_spec.get("template", {}).get("spec", {})
    if pod_spec.get("restartPolicy") != "Never":
        not_passed(f"CronJob jobTemplate pod restartPolicy={pod_spec.get('restartPolicy')!r}, expected 'Never'")

    containers = pod_spec.get("containers", [])
    if not containers:
        not_passed("CronJob jobTemplate pod template has no containers")
    _check_resources(containers[0].get("resources", {}), "CronJob jobTemplate container")

    return cj


def _wait_first_spawned_job():
    state = {}

    def _spawned_and_done():
        data = kubectl_json("get", "jobs", ns=NS, check=False)
        for item in data.get("items", []):
            name = item["metadata"]["name"]
            if name == "rescrape":
                continue
            owners = item["metadata"].get("ownerReferences", [])
            if not any(o.get("kind") == "CronJob" and o.get("name") == "scheduled-scrape" for o in owners):
                continue
            state["name"] = name
            if item.get("status", {}).get("succeeded", 0) >= 1:
                return True
        return False

    wait_until(
        _spawned_and_done,
        timeout=75,
        interval=3,
        desc="CronJob 'scheduled-scrape' to spawn and complete its first Job",
    )
    return state.get("name")


def _suspend_cronjob():
    kubectl(
        "patch", "cronjob", "scheduled-scrape", "--type=merge",
        "-p", '{"spec": {"suspend": true}}', ns=NS,
    )
    cj = kubectl_json("get", "cronjob", "scheduled-scrape", ns=NS)
    if not cj.get("spec", {}).get("suspend"):
        not_passed("patched CronJob 'scheduled-scrape' with suspend: true but spec.suspend did not stick")


@guarded
def main():
    require_cluster()
    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _apply(SRC / "job.yaml")
        _check_job_spec()
        _wait_job_complete()
        pods = _job_pods()
        overlap_detail = _check_overlap_and_qos(pods)

        _apply(SRC / "cronjob.yaml")
        _check_cronjob_spec()
        spawned_name = _wait_first_spawned_job()
        _suspend_cronjob()
        _check_cronjob_spec()  # history-limit fields still correct post-suspend

        n1, n2, latest_start, earliest_finish = overlap_detail
        passed(
            f"Job 'rescrape' reached succeeded=4 with overlapping shard pods {n1}/{n2} "
            f"(overlap window {latest_start.isoformat()} -> {earliest_finish.isoformat()}), resources/QoS correct; "
            f"CronJob 'scheduled-scrape' structurally correct, spawned+completed Job "
            f"'{spawned_name}', now suspended"
        )
    finally:
        delete_ns(NS, wait=False)


if __name__ == "__main__":
    main()
