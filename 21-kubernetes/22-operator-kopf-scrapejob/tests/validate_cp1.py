"""CP1 validator for task 22 (kopf ScrapeJob operator) -- CRD + create.

Runs the learner's `src/operator.py` as a real subprocess (`python -m kopf
run --namespace t22 --verbose`) against the live `sandbox20` cluster,
applies `src/crd.yaml`, then applies one `ScrapeJob` CR and asserts:

  - a child Deployment appears, selected by the label contract from
    README.md (`app.kubernetes.io/managed-by=scrapejob-operator`,
    `scrapejob-name=<CR name>`) -- exactly one such Deployment.
  - it reaches `readyReplicas` equal to the CR's `spec.replicas`.
  - the operator's own log shows a successful create reconcile for this
    CR (kopf's own "Creation is processed: 1 succeeded" summary line,
    scoped to this CR's namespace/name).

With the stub operator (every handler raises NotImplementedError) no
Deployment ever appears -- this fails cleanly rather than vacuously.

Terminates the operator subprocess and cleans up namespace t22 + the CRD
whether this passes or fails.

Run from this task directory (needs the cluster up -- see
`../scripts/cluster-up.sh` from the module root if it isn't):

    uv run python tests/validate_cp1.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    ensure_ns,
    guarded,
    kubectl_json,
    not_passed,
    passed,
    require_cluster,
    wait_until,
)

sys.path.insert(0, str(TASK_ROOT / "tests"))
import _opharness as op  # noqa: E402

CR_NAME = "cp1-crawl"
REPLICAS = 2

CR_YAML = f"""\
apiVersion: sandbox20.dev/v1
kind: ScrapeJob
metadata:
  name: {CR_NAME}
spec:
  replicas: {REPLICAS}
  image: sandbox20-app:1.0
  processMs: 50
"""


def _ready_deployment():
    deps = op.deployments_for(CR_NAME)
    if len(deps) != 1:
        return None
    return deps[0]


@guarded
def main():
    require_cluster()
    op.full_cleanup()

    operator = op.Operator()
    try:
        ensure_ns(op.NS)
        op.apply_crd()

        operator.start(timeout=30)
        op.apply_cr(CR_YAML)

        def _check():
            operator.require_alive("while waiting for the child Deployment to appear")
            dep = _ready_deployment()
            if dep is None:
                return False
            return dep.get("status", {}).get("readyReplicas") == REPLICAS

        wait_until(
            _check, timeout=120, interval=2,
            desc=f"exactly one child Deployment labeled scrapejob-name={CR_NAME} to reach {REPLICAS} ready replicas",
        )

        dep = _ready_deployment()
        dep_name = dep["metadata"]["name"]

        log_text = operator.log_text()
        if f"[{op.NS}/{CR_NAME}]" not in log_text:
            not_passed(f"operator log never mentions [{op.NS}/{CR_NAME}] -- is the create handler registered on the right group/version/plural?")
        if "Creation is processed: 1 succeeded" not in log_text:
            not_passed(
                "operator log never shows a successful create reconcile ('Creation is processed: 1 succeeded') "
                "for this ScrapeJob -- check on_create actually returns instead of raising"
            )

        image = (
            dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("image", "")
        )
        if "sandbox20-app" not in image:
            not_passed(f"child Deployment {dep_name}'s container image is {image!r}, expected the sandbox20-app fixture image")

        passed(
            f"child Deployment {dep_name!r} appeared with {REPLICAS}/{REPLICAS} ready replicas; "
            "operator log shows a successful create reconcile"
        )
    finally:
        operator.stop()
        op.full_cleanup()


if __name__ == "__main__":
    main()
