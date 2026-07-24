# Hint 2

Five pods, five categories of scheduling failure — this task deliberately
covers a spread rather than five variations on one theme. In no
particular order, and not mapped to specific pods here:

- **Resource starvation** — a container asks for more of some resource
  (cpu or memory) than any single node in the cluster has to give,
  even fully empty. No amount of waiting fixes this; the scheduler isn't
  being slow, it's telling you the ask is impossible as written. Check
  `kubectl -n t09 describe node <name>` (`Allocatable`) against what the
  pod requests.
- **A `nodeSelector` referencing a label nothing has** — the pod demands
  a specific label key/value pair via `spec.nodeSelector`, and you check
  `kubectl get nodes --show-labels` and that label simply doesn't exist
  anywhere in this cluster, under any value.
- **A required node affinity rule with the same problem, expressed
  differently** — `spec.affinity.nodeAffinity` with
  `requiredDuringSchedulingIgnoredDuringExecution` is a more expressive,
  more verbose way to say "only nodes matching this" than a plain
  `nodeSelector`, but a required rule that no node satisfies fails
  exactly the same way.
- **A taint with no matching toleration** — the pod is constrained (by
  label or name) to a specific node, and that node has a taint the pod's
  spec doesn't tolerate. This is the one case in this task where the fix
  is additive, not subtractive — see the README's note on `pod-d`.
- **An unbound PersistentVolumeClaim** — the pod itself might have zero
  scheduling constraints and still sit `Pending`, because a volume it
  mounts can't bind. Check the PVC's own events and `status.phase`
  separately from the pod's — `kubectl -n t09 describe pvc zoo-data` and
  `kubectl get storageclass` for what this cluster actually offers.

Match each of the five pods to one of these categories using its own
events output before you touch any YAML.
