# Hint 2

Narrowing each piece:

- **Broker/warehouse reachability**: same two workable routes as
  module 06's bonus — the special hostname docker provides for
  container-to-host traffic, or a kind cluster config with
  `extraPortMappings`. Test both from a pod before touching YAML:
  `kubectl run -it --rm probe --image=busybox -- nc -zv <candidate-host> 19092`
  and the `postgres:16` / `pg_isready` probe from module 06's hint-2.
- **Image into kind**: `kind load docker-image <name:tag>` and
  `pullPolicy: IfNotPresent` (or `Never`) — the default `Always` will
  try a registry pull for a node-local-only tag and fail.
- **The HPA metric**: `type: Resource`, `resource.name: cpu`,
  `resource.target.type: Utilization`,
  `resource.target.averageUtilization: <percent>`. That's the whole
  metric entry for `autoscaling/v2` — it's easy to over-nest this.
  Requires metrics-server in the cluster to actually scale live (not
  required for the offline validator, which only checks the manifest
  shape).
- **The PDB budget**: pick `minAvailable` **or** `maxUnavailable`, not
  both — the validator accepts either but the API rejects a spec that
  sets neither. With `replicas: 2`+ and a rebalance in mind,
  `minAvailable: 1` keeps at least one partition owner alive during a
  voluntary disruption; say in NOTES.md why you picked what you picked.
- **Measuring the consumer**: same metrics-server-or-`docker stats`
  fallback as module 06 — watch it across a few poll cycles under some
  produced load, not at idle.
- **Templating**: minimal — `.Values` plumbing, one consistent label set
  shared by the Deployment's pod template, the HPA's `scaleTargetRef`,
  and the PDB's selector. Define the labels once, reference three times.
