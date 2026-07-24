# Hint 3

No ready-to-paste manifests here, and no exact numbers/labels to copy —
those come from your own `describe`/events output. This is a per-category
walk-through of where to look and what field actually needs to change.

**Resource starvation.** Compare the failing pod's `resources.requests`
against `kubectl -n t09 describe node <name>`'s `Allocatable` section on
every node — not just one node, all of them, since the scheduler rejects
a pod only when *no* node can fit it. If the request is asking for an
amount of a resource that's absurd relative to what any real node in this
cluster has (not "tight," but "impossible"), the fix is bringing that
number down to something an actual node can satisfy alongside whatever
else is already running there. This isn't a field to delete — a container
with no resource requests at all is a different (worse) idea, not the fix
this task wants.

**`nodeSelector` naming a label nothing has.** Run `kubectl get nodes
--show-labels` yourself and look for the exact key the pod's
`spec.nodeSelector` names. If it's genuinely absent from every node in
this cluster — not misspelled, not present with a different value, just
not there — think about what a `nodeSelector` requiring a label with zero
matching nodes actually accomplishes for this workload, and whether the
constraint belongs in the fixed manifest at all.

**Required node affinity naming something nothing has.** Same diagnosis
method, different field: `spec.affinity.nodeAffinity
.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[].
matchExpressions[]`. Check the key it names against actual node labels
(`kubectl get nodes -o jsonpath='{.items[*].metadata.labels}'` or
`--show-labels`) the same way. A *required* rule with zero satisfying
nodes needs the same kind of judgment call as the `nodeSelector` case
above — required affinity isn't a field you can leave half-satisfied.

**Taint with no toleration, on a node the pod must use.** First confirm
the taint's exact key/value/effect (`kubectl describe node
sandbox20-worker2` — the `Taints:` line, or `kubectl get node
sandbox20-worker2 -o jsonpath='{.spec.taints}'`). The fix is adding a
`spec.tolerations` entry to the pod that matches that taint's `key` and
`effect` (`operator: Equal` with the exact `value`, or `operator: Exists`
if you don't need to check the value) — while leaving whatever already
pins this pod to that specific node exactly as it was. Removing the
node-pinning constraint would "fix" scheduling in the sense that the pod
could then land anywhere, but that's not the fix — this pod is required
to land on that specific node, taint and all.

**Unbound PVC.** `kubectl -n t09 describe pvc zoo-data` and its own
events tell you what `storageClassName` it's asking for versus `kubectl
get storageclass` telling you what actually exists (name, and whether one
is marked default). A PVC referencing a `storageClassName` that isn't in
that list will never bind, no matter how long you wait — this isn't a
timing issue. Once the PVC's `storageClassName` matches something real,
also check whether that StorageClass's `VOLUMEBINDINGMODE` is
`WaitForFirstConsumer` — if so, the PVC intentionally stays `Pending`
until a pod that mounts it exists and is being scheduled, which is a
detail worth understanding rather than a second bug to chase.
