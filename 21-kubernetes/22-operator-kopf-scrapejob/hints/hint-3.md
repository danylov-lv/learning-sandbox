# Hint 3

Still no ready-to-paste operator code here -- writing the handler bodies
is the actual assignment. This is the concrete reconcile approach spelled
out step by step, so the only thing left is typing it in Python yourself.

**`src/crd.yaml`'s `spec`, spelled out field by field:**

- `spec.group: sandbox20.dev`, `spec.scope: Namespaced`
- `spec.names.plural: scrapejobs`, `.singular: scrapejob`, `.kind: ScrapeJob`
- `spec.versions` is a list with ONE entry: `name: v1`, `served: true`,
  `storage: true`
- that entry's `schema.openAPIV3Schema` is `type: object` with a
  `properties.spec` that is ALSO `type: object`, whose OWN `properties`
  has exactly three keys (`replicas`, `image`, `processMs`), each an
  object with `type` and `default` (and `minimum` for the two integers)
  -- no `required` list needed, since every field has a default

**`on_create`, as a sequence of steps (not code):**

1. Read `spec['replicas']`, `spec['image']`, `spec['processMs']` -- all
   three are guaranteed present because the CRD schema supplies defaults.
2. Assemble the Deployment dict per hint-2's shape.
3. `kopf.adopt(the_dict)`.
4. `client.AppsV1Api().create_namespaced_deployment(namespace=namespace, body=the_dict)`.
5. Nothing to return -- returning normally (not raising) IS the success
   signal kopf and the validator both look for.

**`on_update`, as a sequence of steps:**

1. Compute the child Deployment's name the same way `on_create` did.
2. Build a small patch body containing only `spec.replicas` (see hint-2).
3. `client.AppsV1Api().patch_namespaced_deployment(dep_name, namespace, patch_body)`.
4. Optional but worth thinking about for `DESIGN.md`: what if the
   Deployment doesn't exist yet when an update arrives (e.g., it was
   deleted out-of-band)? A production operator would re-create it here;
   this task doesn't require that -- name the gap in `DESIGN.md` instead.

**`on_delete`, as a sequence of steps:**

1. Compute the child Deployment's name.
2. Try `client.AppsV1Api().delete_namespaced_deployment(dep_name, namespace)`.
3. Catch `kubernetes.client.exceptions.ApiException`; if `e.status == 404`,
   treat it as success (already gone) instead of re-raising.

**On the CP2 "same `uid`" check specifically:** `patch_namespaced_deployment`
performs a strategic merge patch on the EXISTING object -- Kubernetes
never changes an object's `uid` on an update, only on a delete+recreate.
So as long as `on_update` calls `patch_namespaced_deployment` (not
`delete_namespaced_deployment` followed by `create_namespaced_deployment`),
the `uid` staying constant across the replica change falls out for free --
it's not something you need to engineer separately.

**Sanity-check order, cheapest first:** `kubectl apply -f src/crd.yaml`
alone -> hand-written `ScrapeJob` YAML applied by hand (no operator
running yet) to confirm the schema accepts it -> `kopf run` by hand with
one manually-applied CR, watching `kubectl get deployment -n t22 -w` in a
second terminal -> only then `uv run python tests/validate_cp1.py`.
