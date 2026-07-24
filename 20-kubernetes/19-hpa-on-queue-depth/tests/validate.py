"""Validator for 20-kubernetes task 19 (hpa-on-queue-depth).

Run from this task directory:

    uv run python tests/validate.py

Requires RabbitMQ + Prometheus + prometheus-adapter already installed
cluster-wide (scripts/install.sh -- this task owns that install; it is NOT
reinstalled or uninstalled here). Recreates namespace t19 fresh, applies the
given producer/consumer Deployments plus the learner's src/hpa.yaml, purges
the queue for a clean baseline, then:

  1. drives the producer's rate up so the queue backs up and asserts the
     consumer Deployment's replica count increases within a bounded wait;
  2. stops the producer (scales it to 0) so consumers drain the backlog,
     then asserts replica count decreases again within a bounded wait
     (generous enough for HPA's default 300s scale-down stabilization
     window, in case the learner didn't shorten it).

Namespace t19 is deleted at the end whether the task passes or fails; the
monitoring stack in t19-infra is left installed.
"""

import json
import sys
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
    kubectl,
    kubectl_json,
    not_passed,
    passed,
    require_cluster,
    wait_until,
)

NS = "t19"
INFRA_NS = "t19-infra"
GIVEN = TASK_ROOT / "given"
SRC = TASK_ROOT / "src"
NOTES = TASK_ROOT / "NOTES.md"

QUEUE_NAME = "sandbox20-queue"
RABBIT_USER = "sandbox"
RABBIT_PASS = "sandboxpass"

EXTERNAL_METRIC_NAME = "rabbitmq_queue_messages_ready"
EXTERNAL_METRIC_PATH = (
    f"/apis/external.metrics.k8s.io/v1beta1/namespaces/{NS}/{EXTERNAL_METRIC_NAME}"
    f"?labelSelector=queue%3D{QUEUE_NAME}"
)

HIGH_RATE_PER_S = "40"  # pushes far past the baseline 2/s producer / 2/s-per-replica consumer balance

# HPA sync period is ~15s and scale-up has no stabilization window by
# default, but a cold metrics-relist + a couple of HPA polling cycles can
# take a bit -- generous, bounded, no wall-clock assumption.
SCALE_UP_TIMEOUT_S = 300
# HPA's default scaleDown.stabilizationWindowSeconds is 300s; a learner
# who didn't shorten it still needs to pass, plus drain time for whatever
# backlog built up during the scale-up phase -- generous on purpose.
DRAIN_AND_SCALE_DOWN_TIMEOUT_S = 900


def _require_monitoring_stack():
    fix = "run `bash scripts/install.sh` from this task directory first"

    rabbitmq = kubectl_json("get", "deployment", "rabbitmq", ns=INFRA_NS, check=False)
    if not rabbitmq or not rabbitmq.get("status", {}).get("readyReplicas"):
        not_passed(f"RabbitMQ not installed/ready in namespace '{INFRA_NS}' -- {fix}")

    prometheus = kubectl_json("get", "deployment", "prometheus", ns=INFRA_NS, check=False)
    if not prometheus or not prometheus.get("status", {}).get("readyReplicas"):
        not_passed(f"Prometheus not installed/ready in namespace '{INFRA_NS}' -- {fix}")

    adapter = kubectl_json("get", "deployment", "prometheus-adapter", ns=INFRA_NS, check=False)
    if not adapter or not adapter.get("status", {}).get("readyReplicas"):
        not_passed(f"prometheus-adapter not installed/ready in namespace '{INFRA_NS}' -- {fix}")

    apisvc = kubectl_json("get", "apiservice", "v1beta1.external.metrics.k8s.io", check=False)
    conditions = {c.get("type"): c.get("status") for c in apisvc.get("status", {}).get("conditions", [])}
    if conditions.get("Available") != "True":
        not_passed(f"external.metrics.k8s.io APIService not Available -- {fix}")


def _queue_depth():
    """Returns the live queue depth via the same external metrics API path
    an HPA would query, or None if the API isn't answering yet."""
    result = kubectl("get", "--raw", EXTERNAL_METRIC_PATH, check=False, timeout=20)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    items = data.get("items", [])
    if not items:
        return None
    try:
        return float(items[0]["value"])
    except (KeyError, ValueError):
        return None


def _require_metric_live():
    def _check() -> bool:
        return _queue_depth() is not None

    wait_until(
        _check, timeout=60, interval=3,
        desc=(
            f"the external metric '{EXTERNAL_METRIC_NAME}' to be queryable at "
            f"{EXTERNAL_METRIC_PATH} -- run scripts/install.sh if this never comes up"
        ),
    )


def _purge_queue():
    pod_data = kubectl_json("get", "pod", "-l", "app=rabbitmq", ns=INFRA_NS, check=False)
    items = pod_data.get("items", [])
    if not items:
        not_passed(f"no rabbitmq pod found in namespace '{INFRA_NS}' -- run scripts/install.sh first")
    pod_name = items[0]["metadata"]["name"]
    result = kubectl(
        "exec", pod_name, "--", "rabbitmqadmin",
        "-u", RABBIT_USER, "-p", RABBIT_PASS,
        "purge", "queue", f"name={QUEUE_NAME}",
        ns=INFRA_NS, check=False, timeout=30,
    )
    if result.returncode != 0:
        not_passed(f"purging queue '{QUEUE_NAME}' before the run failed: {result.stderr.strip()}")


def _apply(path: Path):
    result = kubectl("apply", "-f", str(path), ns=NS, check=False, timeout=60)
    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()
        not_passed(f"kubectl apply -f {path.name} failed: {err}")


def _check_hpa_applied():
    hpa = kubectl_json("get", "hpa", "queue-consumer-hpa", ns=NS, check=False)
    if not hpa:
        not_passed(
            "HorizontalPodAutoscaler 'queue-consumer-hpa' not found in namespace t19 after apply -- "
            "did you set metadata.name: queue-consumer-hpa? (src/hpa.yaml is a TODO comment block that "
            "applies nothing until you replace it with a real HPA)"
        )
    spec = hpa.get("spec", {})
    target = spec.get("scaleTargetRef", {})
    if target.get("kind") != "Deployment" or target.get("name") != "queue-consumer":
        not_passed(
            f"HPA 'queue-consumer-hpa' scaleTargetRef={target!r}, expected a Deployment named 'queue-consumer'"
        )
    metrics = spec.get("metrics", [])
    external = [m for m in metrics if m.get("type") == "External"]
    if not external:
        not_passed("HPA 'queue-consumer-hpa' has no metrics of type 'External' -- this task requires one")
    metric_name = external[0].get("external", {}).get("metric", {}).get("name")
    if metric_name != EXTERNAL_METRIC_NAME:
        not_passed(
            f"HPA's External metric name={metric_name!r}, expected {EXTERNAL_METRIC_NAME!r} "
            "(the metric exposed by prometheus-adapter -- see README)"
        )


def _consumer_replicas() -> int:
    """spec.replicas, not status.replicas -- this is what the HPA controller
    itself sets (via the scale subresource) the instant it decides to act,
    without waiting for the new/old pods to actually finish starting/stopping."""
    dep = kubectl_json("get", "deployment", "queue-consumer", ns=NS, check=False)
    return dep.get("spec", {}).get("replicas", 0) or 0


def _drive_scale_up():
    kubectl("set", "env", "deployment/queue-producer", f"RATE_PER_S={HIGH_RATE_PER_S}", ns=NS, check=False, timeout=30)
    kubectl("rollout", "status", "deployment/queue-producer", "--timeout=60s", ns=NS, check=False, timeout=70)

    baseline = _consumer_replicas()

    def _scaled_up() -> bool:
        return _consumer_replicas() > baseline

    wait_until(
        _scaled_up, timeout=SCALE_UP_TIMEOUT_S, interval=5,
        desc=(
            f"queue-consumer replicas to increase above the baseline of {baseline} once the "
            "producer's rate is raised and the queue backs up"
        ),
    )
    return baseline, _consumer_replicas()


def _drain_and_wait_scale_down(peak_replicas: int):
    kubectl("scale", "deployment/queue-producer", "--replicas=0", ns=NS, check=False, timeout=30)

    def _drained() -> bool:
        depth = _queue_depth()
        return depth is not None and depth <= 0

    wait_until(
        _drained, timeout=DRAIN_AND_SCALE_DOWN_TIMEOUT_S, interval=5,
        desc=f"queue '{QUEUE_NAME}' to drain to 0 after stopping the producer",
    )

    def _scaled_down() -> bool:
        return _consumer_replicas() < peak_replicas

    wait_until(
        _scaled_down, timeout=DRAIN_AND_SCALE_DOWN_TIMEOUT_S, interval=5,
        desc=(
            f"queue-consumer replicas to decrease below the peak of {peak_replicas} after the queue "
            "drained (HPA scale-down stabilization can legitimately take several minutes)"
        ),
    )
    return _consumer_replicas()


REQUIRED_SECTIONS = [
    "The external metrics pipeline",
    "Why queue depth, not CPU",
    "Scaling observations",
    "AverageValue arithmetic",
]

KEYWORDS = [
    "External", "external.metrics.k8s.io", "prometheus-adapter", "Prometheus",
    "RabbitMQ", "queue depth", "AverageValue", "stabilizationWindowSeconds",
    "scale up", "scale down", "CPU", "I/O", "replicas", "ceil",
]


def _check_notes():
    sections = check_sections(NOTES, REQUIRED_SECTIONS, min_chars=250)
    full_text = "\n\n".join(sections.values())
    check_keywords(full_text, KEYWORDS, min_hits=8, label="NOTES.md")


@guarded
def main():
    require_cluster()
    _require_monitoring_stack()
    _require_metric_live()

    delete_ns(NS, wait=True)
    ensure_ns(NS)
    try:
        _purge_queue()

        _apply(GIVEN / "producer.yaml")
        _apply(GIVEN / "consumer.yaml")
        kubectl("rollout", "status", "deployment/queue-producer", "--timeout=90s", ns=NS, timeout=100)
        kubectl("rollout", "status", "deployment/queue-consumer", "--timeout=90s", ns=NS, timeout=100)

        _apply(SRC / "hpa.yaml")
        _check_hpa_applied()

        baseline, peak_after_up = _drive_scale_up()
        final_replicas = _drain_and_wait_scale_down(peak_after_up)

        _check_notes()

        passed(
            f"queue-consumer replicas went {baseline} -> {peak_after_up} (queue backed up) -> "
            f"{final_replicas} (queue drained) within bounded waits"
        )
    finally:
        kubectl("delete", "hpa", "queue-consumer-hpa", ns=NS, check=False, timeout=30)
        delete_ns(NS, wait=False)
        _purge_queue()


if __name__ == "__main__":
    main()
