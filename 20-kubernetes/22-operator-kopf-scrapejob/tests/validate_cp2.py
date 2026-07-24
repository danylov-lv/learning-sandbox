"""CP2 validator for task 22 (kopf ScrapeJob operator) -- update + delete.

Same live-operator-as-subprocess setup as CP1 (see `_opharness.py`), then:

  1. Applies a ScrapeJob CR with `spec.replicas: 1`, waits for the child
     Deployment to reach 1 ready replica -- and captures its `uid`.
  2. Patches the CR to `spec.replicas: 3`, waits for the SAME Deployment
     (same `uid` -- proof the operator patched the existing object rather
     than deleting and recreating it) to reach 3 ready replicas.
  3. Deletes the CR, asserts the child Deployment disappears within a
     bounded wait.
  4. Greps the operator's captured log for kopf's own reconcile-summary
     lines: a successful update ("Updating is processed: 1 succeeded")
     and a successful delete ("Deletion is processed: 1 succeeded"), both
     scoped to this CR's namespace/name.

With the stub operator (on_update / on_delete raise NotImplementedError)
the replica count never changes and the Deployment is never removed --
this fails cleanly rather than vacuously.

Terminates the operator subprocess and cleans up namespace t22 + the CRD
whether this passes or fails.

Run from this task directory (needs the cluster up):

    uv run python tests/validate_cp2.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    ensure_ns,
    guarded,
    kubectl,
    not_passed,
    passed,
    require_cluster,
    wait_until,
)

sys.path.insert(0, str(TASK_ROOT / "tests"))
import _opharness as op  # noqa: E402

CR_NAME = "cp2-crawl"
INITIAL_REPLICAS = 1
UPDATED_REPLICAS = 3

CR_YAML = f"""\
apiVersion: sandbox20.dev/v1
kind: ScrapeJob
metadata:
  name: {CR_NAME}
spec:
  replicas: {INITIAL_REPLICAS}
  image: sandbox20-app:1.0
  processMs: 50
"""


def _single_deployment():
    deps = op.deployments_for(CR_NAME)
    return deps[0] if len(deps) == 1 else None


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

        def _initial_ready():
            operator.require_alive("while waiting for the initial child Deployment")
            dep = _single_deployment()
            return dep is not None and dep.get("status", {}).get("readyReplicas") == INITIAL_REPLICAS

        wait_until(_initial_ready, timeout=120, interval=2, desc=f"child Deployment to reach {INITIAL_REPLICAS} ready replica")

        dep_before = _single_deployment()
        dep_name = dep_before["metadata"]["name"]
        uid_before = dep_before["metadata"]["uid"]

        patch_result = kubectl(
            "patch", "scrapejob", CR_NAME, "--type=merge", "-p",
            f'{{"spec":{{"replicas":{UPDATED_REPLICAS}}}}}',
            ns=op.NS, check=False, timeout=20,
        )
        if patch_result.returncode != 0:
            not_passed(f"kubectl patch scrapejob/{CR_NAME} failed: {patch_result.stderr.strip()}")

        def _updated_ready():
            operator.require_alive("while waiting for the reconciled replica count")
            dep = _single_deployment()
            if dep is None:
                return False
            same_object = dep["metadata"]["uid"] == uid_before
            if not same_object:
                not_passed(
                    f"child Deployment's uid changed after the replica update ({uid_before} -> "
                    f"{dep['metadata']['uid']}) -- on_update must patch the existing Deployment, not "
                    "delete and recreate it"
                )
            return dep.get("status", {}).get("readyReplicas") == UPDATED_REPLICAS

        wait_until(_updated_ready, timeout=120, interval=2, desc=f"same child Deployment to reach {UPDATED_REPLICAS} ready replicas")

        delete_result = kubectl("delete", "scrapejob", CR_NAME, "--wait=true", ns=op.NS, check=False, timeout=60)
        if delete_result.returncode != 0:
            not_passed(f"kubectl delete scrapejob/{CR_NAME} failed or timed out: {delete_result.stderr.strip()}")

        def _deployment_gone():
            operator.require_alive("while waiting for the child Deployment to be cleaned up")
            return len(op.deployments_for(CR_NAME)) == 0

        wait_until(_deployment_gone, timeout=60, interval=2, desc=f"child Deployment {dep_name} to disappear after CR deletion")

        log_text = operator.log_text()
        scope = f"[{op.NS}/{CR_NAME}]"
        if scope not in log_text:
            not_passed(f"operator log never mentions {scope}")
        if "Updating is processed: 1 succeeded" not in log_text:
            not_passed(
                "operator log never shows a successful update reconcile ('Updating is processed: 1 succeeded') "
                "-- check on_update is registered and returns instead of raising"
            )
        if "Deletion is processed: 1 succeeded" not in log_text:
            not_passed(
                "operator log never shows a successful delete reconcile ('Deletion is processed: 1 succeeded') "
                "-- check on_delete is registered and returns instead of raising"
            )

        passed(
            f"Deployment {dep_name!r} reconciled {INITIAL_REPLICAS}->{UPDATED_REPLICAS} replicas in place "
            f"(uid unchanged) then removed on CR deletion; update and delete reconciles both logged"
        )
    finally:
        operator.stop()
        op.full_cleanup()


if __name__ == "__main__":
    main()
