"""ScrapeJob operator -- kopf handlers you must implement.

The validator runs this file directly, as a subprocess, exactly like this:

    uv run python -m kopf run src/operator.py --namespace t22 --verbose

See README.md "Schema contract" for the exact CRD group/version/plural and
the label contract the validator selects child Deployments by -- both are
given below as constants so a typo can't silently break the contract.

Given, not the assignment: imports, the CRD identity constants, the two
labels every child Deployment must carry, and a naming helper. Everything
else -- building the Deployment manifest, calling the Kubernetes API,
wiring up the owner reference, patching on update, deleting on delete --
is yours to write.
"""

from __future__ import annotations

import kopf
from kubernetes import client

GROUP = "sandbox20.dev"
VERSION = "v1"
PLURAL = "scrapejobs"

# Every child Deployment this operator creates MUST carry both of these
# labels (see README.md "Schema contract") -- the validators select
# resources by them, not by name, so you're free to name the Deployment
# itself however you like.
MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "scrapejob-operator"
NAME_LABEL = "scrapejob-name"


def worker_deployment_name(scrapejob_name: str) -> str:
    return f"{scrapejob_name}-worker"


@kopf.on.create(GROUP, VERSION, PLURAL)
def on_create(spec, name, namespace, logger, **kwargs):
    """A new ScrapeJob showed up. Create its child worker Deployment.

    TODO(you):
      - Build a Deployment (apps/v1) manifest for the worker pool:
          * metadata.labels AND spec.template.metadata.labels both carry
            {MANAGED_BY_LABEL: MANAGED_BY_VALUE, NAME_LABEL: name}
          * spec.selector.matchLabels matches the pod template labels
          * spec.replicas comes from spec['replicas']
          * one container running spec['image'], with env var
            PROCESS_MS set from spec['processMs']
      - Call kopf.adopt(manifest) before creating it, so the Deployment
        gets an ownerReference back to this ScrapeJob (GC as a backstop --
        on_delete below must not rely on GC alone).
      - Create it via kubernetes.client.AppsV1Api().create_namespaced_deployment(...).
    """
    raise NotImplementedError


@kopf.on.update(GROUP, VERSION, PLURAL)
def on_update(spec, name, namespace, logger, **kwargs):
    """The ScrapeJob's spec changed. Reconcile the child Deployment to match.

    TODO(you): at minimum, patch the existing worker Deployment's
    spec.replicas to spec['replicas']. Patch the SAME object -- don't
    delete and recreate it (validate_cp2.py checks the Deployment's uid
    is unchanged across an update).
    """
    raise NotImplementedError


@kopf.on.delete(GROUP, VERSION, PLURAL)
def on_delete(spec, name, namespace, logger, **kwargs):
    """The ScrapeJob was deleted. Remove its child worker Deployment.

    TODO(you): delete the worker Deployment yourself. The ownerReference
    from on_create would let Kubernetes garbage-collect it too, but this
    handler must not depend on that timing -- delete it explicitly so
    cleanup is immediate. Handle the case where it's already gone (404)
    without raising.
    """
    raise NotImplementedError
