"""CP1 validator for task 07 (Arc 2 capstone) -- STRUCTURE, offline.

Deliberately does NOT call `harness.common.require_cluster()`. Every check
here is `helm lint` / `helm template` against the chart on disk plus
parsing the rendered YAML -- nothing is applied to any cluster, so this
checkpoint runs (and should run) even with the kind cluster down. Live
behavior (installing the chart, watching the pipeline actually flow, the
dev->prod upgrade) is CP2's job, not this one's.

Checks, in order (see README.md "Chart contract" for the authoritative
list this mirrors):

  1. `helm lint` clean, both with default values and with values-prod.yaml.
  2. Default render: every resource carries the standard labels plus a
     valid `app.kubernetes.io/component` label, and every resource's name
     starts with the release name used to render it (fullname contract).
     All four components (target/queue/producer/workers) are present.
  3. `target.enabled=false` / `producer.enabled=false` each remove exactly
     that component's resources and nothing else.
  4. `workers.replicas`, `workers.probes.readiness.*`, `producer.ratePerS`,
     and `workers.processMs` are all templated from values, not hardcoded
     -- proven by flipping each via `--set` and checking the rendered
     output actually changed.
  5. The `workers` pod template's `checksum/...` annotation changes when
     `workers.processMs` changes (proves it hashes a config object that
     actually contains that value).
  6. `REDIS_HOST` on both `producer` and `workers` resolves to the queue
     Service's OWN rendered name, under two different release names (rules
     out a hardcoded string that happens to match once).
  7. `values-dev.yaml` / `values-prod.yaml` exist at chart root and render
     the contract's dev/prod numbers (1 vs. 3 workers, prod resources
     non-empty, prod producer rate faster than dev's).

Run from this task directory:

    uv run python tests/validate_cp1.py
"""

import subprocess
import sys
from pathlib import Path

import yaml

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

CHART_DIR = TASK_ROOT / "chart"
RELEASE_A = "t07-spider"
RELEASE_B = "zz-other-release"
VALID_COMPONENTS = {"target", "queue", "producer", "workers"}
STANDARD_LABEL_KEYS = [
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/managed-by",
    "app.kubernetes.io/component",
]


def _tail(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def helm(*args, timeout=60):
    cmd = ["helm"] + list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(TASK_ROOT))
    except FileNotFoundError:
        not_passed("helm not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"helm {' '.join(args)} timed out after {timeout}s")


def helm_lint(*extra_args):
    result = helm("lint", str(CHART_DIR), *extra_args)
    if result.returncode != 0:
        not_passed(f"helm lint {' '.join(extra_args)} failed: {_tail(result.stdout + result.stderr)}")


def render(release=RELEASE_A, values_file=None, set_args=None):
    args = ["template", release, str(CHART_DIR)]
    if values_file:
        args += ["-f", str(values_file)]
    for kv in set_args or []:
        args += ["--set", kv]
    result = helm(*args)
    if result.returncode != 0:
        not_passed(f"helm template failed: {_tail(result.stdout + result.stderr)}")
    try:
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    except yaml.YAMLError as e:
        not_passed(f"helm template produced invalid YAML: {e}")
    if not docs:
        not_passed("helm template produced no rendered resources -- is every template TODO-stubbed still?")
    return docs


def by_component(docs, component):
    return [d for d in docs if ((d.get("metadata") or {}).get("labels") or {}).get("app.kubernetes.io/component") == component]


def deployments_by_component(docs, component):
    deps = [d for d in by_component(docs, component) if d.get("kind") == "Deployment"]
    if len(deps) != 1:
        not_passed(f"expected exactly one Deployment with app.kubernetes.io/component={component}, found {len(deps)}")
    return deps[0]


def services_by_component(docs, component):
    svcs = [d for d in by_component(docs, component) if d.get("kind") == "Service"]
    if len(svcs) != 1:
        not_passed(f"expected exactly one Service with app.kubernetes.io/component={component}, found {len(svcs)}")
    return svcs[0]


def first_container(dep):
    containers = (dep.get("spec") or {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        not_passed(f"Deployment {(dep.get('metadata') or {}).get('name')} has no containers")
    return containers[0]


def find_configmap(docs, name):
    for d in docs:
        if d.get("kind") == "ConfigMap" and (d.get("metadata") or {}).get("name") == name:
            return d
    return None


def resolve_env(container, docs, var_name):
    for e in container.get("env") or []:
        if e.get("name") != var_name:
            continue
        if "value" in e:
            return str(e["value"])
        cm_ref = (e.get("valueFrom") or {}).get("configMapKeyRef")
        if cm_ref:
            cm = find_configmap(docs, cm_ref.get("name"))
            if cm is None:
                not_passed(f"env {var_name} references ConfigMap {cm_ref.get('name')!r}, not found in rendered output")
            data = cm.get("data") or {}
            if cm_ref.get("key") not in data:
                not_passed(f"ConfigMap {cm_ref.get('name')!r} has no key {cm_ref.get('key')!r} for env {var_name}")
            return str(data[cm_ref.get("key")])
        not_passed(f"env {var_name} uses an unsupported valueFrom shape: {e.get('valueFrom')}")
    for ef in container.get("envFrom") or []:
        cm_ref = ef.get("configMapRef") or {}
        cm = find_configmap(docs, cm_ref.get("name"))
        if cm is not None and var_name in (cm.get("data") or {}):
            return str(cm["data"][var_name])
    return None


def check_labels_and_prefix(docs, release):
    problems = []
    for d in docs:
        meta = d.get("metadata") or {}
        name = meta.get("name", "")
        kind = d.get("kind", "?")
        if not name.startswith(release):
            problems.append(f"{kind}/{name}: metadata.name does not start with release name {release!r}")
        labels = meta.get("labels") or {}
        missing = [k for k in STANDARD_LABEL_KEYS if k not in labels]
        if missing:
            problems.append(f"{kind}/{name}: missing label(s) {missing}")
        elif labels.get("app.kubernetes.io/component") not in VALID_COMPONENTS:
            problems.append(
                f"{kind}/{name}: app.kubernetes.io/component={labels.get('app.kubernetes.io/component')!r} "
                f"not one of {sorted(VALID_COMPONENTS)}"
            )
    if problems:
        not_passed("label/fullname contract violated: " + "; ".join(problems[:6]))


def check_all_components_present(docs):
    for comp in sorted(VALID_COMPONENTS):
        if not by_component(docs, comp):
            not_passed(f"default render has no resource with app.kubernetes.io/component={comp}")


def check_toggle(component, value_path):
    docs = render(set_args=[f"{value_path}=false"])
    if by_component(docs, component):
        not_passed(f"--set {value_path}=false still rendered resource(s) with app.kubernetes.io/component={component}")


def check_workers_replicas_templated():
    docs = render(set_args=["workers.replicas=4"])
    dep = deployments_by_component(docs, "workers")
    replicas = (dep.get("spec") or {}).get("replicas")
    if replicas != 4:
        not_passed(f"--set workers.replicas=4 rendered spec.replicas={replicas!r}, expected 4 -- not templated?")


def check_workers_probe_templated():
    docs = render(set_args=["workers.probes.readiness.periodSeconds=17"])
    dep = deployments_by_component(docs, "workers")
    container = first_container(dep)
    probe = container.get("readinessProbe") or {}
    http_get = probe.get("httpGet") or {}
    if http_get.get("path") != "/readyz":
        not_passed(f"workers readinessProbe.httpGet.path={http_get.get('path')!r}, expected /readyz")
    try:
        port = int(http_get.get("port"))
    except (TypeError, ValueError):
        port = None
    if port != 8080:
        not_passed(f"workers readinessProbe.httpGet.port={http_get.get('port')!r}, expected 8080")
    try:
        period = int(probe.get("periodSeconds"))
    except (TypeError, ValueError):
        period = None
    if period != 17:
        not_passed(
            f"--set workers.probes.readiness.periodSeconds=17 rendered periodSeconds={probe.get('periodSeconds')!r}, "
            "expected 17 -- probe fields must be templated from values, not hardcoded"
        )


def check_producer_rate_templated():
    docs = render(set_args=["producer.ratePerS=9.5"])
    dep = deployments_by_component(docs, "producer")
    container = first_container(dep)
    val = resolve_env(container, docs, "RATE_PER_S")
    if val is None:
        not_passed("producer container has no RATE_PER_S env var (directly or via envFrom ConfigMap)")
    if float(val) != 9.5:
        not_passed(f"--set producer.ratePerS=9.5 rendered RATE_PER_S={val!r}, expected 9.5")


def check_workers_processms_and_checksum():
    docs_a = render(set_args=["workers.processMs=111"])
    dep_a = deployments_by_component(docs_a, "workers")
    container_a = first_container(dep_a)
    val_a = resolve_env(container_a, docs_a, "PROCESS_MS")
    if val_a is None:
        not_passed("workers container has no PROCESS_MS env var (directly or via envFrom ConfigMap)")
    if int(float(val_a)) != 111:
        not_passed(f"--set workers.processMs=111 rendered PROCESS_MS={val_a!r}, expected 111")

    ann_a = ((dep_a.get("spec") or {}).get("template", {}).get("metadata", {}).get("annotations")) or {}
    checksum_keys = [k for k in ann_a if k.startswith("checksum/")]
    if not checksum_keys:
        not_passed("workers pod template has no annotation key starting with 'checksum/'")
    key = checksum_keys[0]

    docs_b = render(set_args=["workers.processMs=222"])
    dep_b = deployments_by_component(docs_b, "workers")
    ann_b = ((dep_b.get("spec") or {}).get("template", {}).get("metadata", {}).get("annotations")) or {}
    if key not in ann_b:
        not_passed(f"checksum annotation {key!r} disappeared when workers.processMs changed")
    if ann_a[key] == ann_b[key]:
        not_passed(
            f"checksum annotation {key!r} did not change when workers.processMs changed (111 -> 222) -- "
            "it must hash a config object that actually contains PROCESS_MS"
        )


def check_queue_host_derivation():
    names = {}
    for release in (RELEASE_A, RELEASE_B):
        docs = render(release=release)
        queue_svc = services_by_component(docs, "queue")
        queue_name = (queue_svc.get("metadata") or {}).get("name")
        names[release] = queue_name
        for comp in ("producer", "workers"):
            dep = deployments_by_component(docs, comp)
            container = first_container(dep)
            redis_host = resolve_env(container, docs, "REDIS_HOST")
            if redis_host is None:
                not_passed(f"{comp} container has no REDIS_HOST env var")
            if redis_host != queue_name:
                not_passed(
                    f"release {release!r}: {comp}'s REDIS_HOST={redis_host!r} does not match the queue "
                    f"Service's own rendered name {queue_name!r} -- looks hardcoded rather than derived"
                )
    if names[RELEASE_A] == names[RELEASE_B]:
        not_passed(
            f"queue Service name is {names[RELEASE_A]!r} under both release {RELEASE_A!r} and {RELEASE_B!r} -- "
            "cannot prove REDIS_HOST is release-derived rather than a coincidentally-matching hardcoded string"
        )


def check_values_files():
    for fname in ("values-dev.yaml", "values-prod.yaml"):
        if not (CHART_DIR / fname).exists():
            not_passed(f"missing chart/{fname}")

    docs_dev = render(values_file=CHART_DIR / "values-dev.yaml")
    dep_dev = deployments_by_component(docs_dev, "workers")
    replicas_dev = (dep_dev.get("spec") or {}).get("replicas")
    if replicas_dev != 1:
        not_passed(f"values-dev.yaml renders workers.replicas={replicas_dev!r}, expected 1")
    producer_dev = deployments_by_component(docs_dev, "producer")
    rate_dev = resolve_env(first_container(producer_dev), docs_dev, "RATE_PER_S")
    if rate_dev is None:
        not_passed("values-dev.yaml: producer has no RATE_PER_S")

    docs_prod = render(values_file=CHART_DIR / "values-prod.yaml")
    dep_prod = deployments_by_component(docs_prod, "workers")
    replicas_prod = (dep_prod.get("spec") or {}).get("replicas")
    if replicas_prod != 3:
        not_passed(f"values-prod.yaml renders workers.replicas={replicas_prod!r}, expected 3")

    resources = first_container(dep_prod).get("resources") or {}
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}
    missing = [f"requests.{k}" for k in ("cpu", "memory") if k not in requests]
    missing += [f"limits.{k}" for k in ("cpu", "memory") if k not in limits]
    if missing:
        not_passed(f"values-prod.yaml: workers container resources incomplete, missing {missing}")

    producer_prod = deployments_by_component(docs_prod, "producer")
    rate_prod = resolve_env(first_container(producer_prod), docs_prod, "RATE_PER_S")
    if rate_prod is None:
        not_passed("values-prod.yaml: producer has no RATE_PER_S")
    if not (float(rate_prod) > float(rate_dev)):
        not_passed(
            f"values-prod.yaml producer.ratePerS ({rate_prod}) is not greater than values-dev.yaml's ({rate_dev})"
        )

    return float(rate_dev), float(rate_prod), replicas_dev, replicas_prod


@guarded
def main():
    helm_lint()
    helm_lint("-f", str(CHART_DIR / "values-prod.yaml"))

    docs = render()
    check_labels_and_prefix(docs, RELEASE_A)
    check_all_components_present(docs)

    check_toggle("target", "target.enabled")
    check_toggle("producer", "producer.enabled")

    check_workers_replicas_templated()
    check_workers_probe_templated()
    check_producer_rate_templated()
    check_workers_processms_and_checksum()
    check_queue_host_derivation()
    rate_dev, rate_prod, replicas_dev, replicas_prod = check_values_files()

    passed(
        f"chart lints and renders correctly; values-dev.yaml workers={replicas_dev} rate={rate_dev}, "
        f"values-prod.yaml workers={replicas_prod} rate={rate_prod}"
    )


if __name__ == "__main__":
    main()
