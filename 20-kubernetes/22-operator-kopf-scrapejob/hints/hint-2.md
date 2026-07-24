# Hint 2

**`on_create`'s shape.** Build a plain Python `dict` shaped like a
Deployment manifest (`apiVersion: apps/v1`, `kind: Deployment`, the usual
`metadata`/`spec.replicas`/`spec.selector.matchLabels`/`spec.template`
nesting) -- the exact same structure you'd write as YAML, just as nested
dicts/lists. Both `metadata.labels` on the Deployment itself AND
`spec.template.metadata.labels` on the pod template need
`MANAGED_BY_LABEL`/`NAME_LABEL` from the constants already given; `spec.
selector.matchLabels` needs to match whatever subset of those you put on
the pod template (matching on `NAME_LABEL` alone is enough -- it's already
unique per `ScrapeJob`). Call `kopf.adopt(your_dict)` on that manifest
BEFORE creating it -- it mutates the dict in place to add an
`ownerReferences` entry pointing back at the `ScrapeJob`, using data kopf
already has from the handler's context. Then hand the dict to
`client.AppsV1Api().create_namespaced_deployment(namespace=namespace,
body=your_dict)`.

**`on_update`'s shape.** You don't need to rebuild the whole Deployment --
a merge/strategic patch is enough. `client.AppsV1Api().
patch_namespaced_deployment(name, namespace, body)` with `body` being just
`{"spec": {"replicas": spec['replicas']}}` patches only that field,
leaving everything else (image, labels, container definition) untouched.
This is also why you need a way to know the child Deployment's name from
inside `on_update` -- reuse the exact same naming scheme `on_create` used
(the given `worker_deployment_name` helper, or whatever else you settled
on, as long as both handlers agree).

**`on_delete`'s shape.** `client.AppsV1Api().delete_namespaced_deployment(name,
namespace)`. Wrap it so a 404 (Deployment already gone -- maybe GC beat
you to it, maybe this is a retry of an already-succeeded delete) doesn't
make the handler raise: catch `kubernetes.client.exceptions.ApiException`
and re-raise unless `e.status == 404`. An `on_delete` that raises on
"already deleted" turns a no-op retry into a permanent failure -- kopf
will keep the ScrapeJob's finalizer in place and retry forever.

**Reading the validator's own log-grep expectations tells you what "done"
looks like without needing to invent your own logging.** kopf itself
prints a summary line per reconcile cycle -- something like `Creation is
processed: 1 succeeded; 0 failed.` -- at INFO level, scoped with
`[namespace/name]`, whenever a handler for that lifecycle event returns
without raising. You don't have to construct this string yourself; it
comes free from the framework the moment your handler stops raising
`NotImplementedError`. If you want your own log line too,
`logger.info(...)` inside a handler is scoped the same way automatically.
