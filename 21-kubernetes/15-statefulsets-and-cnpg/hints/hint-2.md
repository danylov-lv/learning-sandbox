# Hint 2

Writing `src/cluster.yaml` is closer to writing a Deployment than it
might look — it's still just YAML with `apiVersion`/`kind`/`metadata`/
`spec` — the difference is that `apiVersion: postgresql.cnpg.io/v1` and
`kind: Cluster` only mean something *after* `scripts/install.sh` has
registered that CRD with the API server. Before that, `kubectl apply`
against a perfectly well-formed `Cluster` YAML fails with "no matches
for kind Cluster" — that's a different failure than the stub's "applies
nothing," so if you see it, check the operator is actually installed
first.

The fields this task grades are deliberately few:

- `spec.instances: 3` — CNPG reads this as "maintain exactly this many
  instances: 1 primary + (instances - 1) streaming replicas," and
  reconciles toward it continuously, the same way a Deployment's
  `replicas` field works, just with much more domain logic behind what
  "maintain" means for a database.
- `spec.imageName` — which Postgres container image each instance runs.
  CNPG publishes a whole catalog of maintained Postgres versions under
  `ghcr.io/cloudnative-pg/postgresql`; you don't have to build anything,
  just pick a tag (this task tells you which one is pre-verified to
  pull against this cluster).
- `spec.storage.size` / `spec.storage.storageClass` — how big a PVC to
  request per instance, and from which `StorageClass`. This cluster's
  default (and only) `StorageClass` is `standard`
  (`rancher.io/local-path`) — check for yourself with `kubectl get
  storageclass`.

Everything else (the actual bootstrap method, replication slots, the
superuser credentials Secret) has a sane CNPG default when you don't
specify it — you don't need to write more than the fields above for a
working 3-instance cluster in a lab like this one.
