# 09 — Pending pod zoo

## Backstory

Someone deployed the scraping fleet on Friday afternoon and left for the
weekend. Monday morning: five pods, none Running. Not crash-looping, not
erroring — just sitting in `Pending` forever, like the scheduler looked at
each of them once and quietly gave up. No logs to read, because none of
these containers ever started. Whatever's wrong here happened before a
single line of application code ran.

This is the other half of debugging Kubernetes: not every broken workload
fails loudly. A pod stuck `Pending` is the scheduler telling you, in its
own vocabulary, that it couldn't find a node that satisfies every
constraint on the pod spec — and that vocabulary lives in `kubectl
describe pod` and `kubectl get events`, not in `kubectl logs`. Five pods,
five different constraints, five different reasons the scheduler said no.

## What's given

```bash
bash given/setup.sh
```

resets namespace `t09` from scratch, taints node `sandbox20-worker2` with
`s20-t09/quarantine=true:NoSchedule`, and applies `given/zoo.yaml`: five
Pods (`pod-a` .. `pod-e`) plus a PersistentVolumeClaim (`zoo-data`) that
`pod-e` mounts. All five pods are expected to sit in `Pending` — that's
the starting state, not a bug in the fixture.

Don't read `given/zoo.yaml` before you've looked at the live cluster —
the point of this task is diagnosing from `describe`/events output, the
same way you would against a workload you didn't write yourself.

The quarantine taint on `sandbox20-worker2` is part of the fixture, not
an accident: leave it in place for the whole task. Your fix for `pod-d`
has to work *with* the taint present, not by getting rid of it (see
`fixes/pod-d.yaml`'s stub comment and "What's required" below).

## What's required

For each of the five pods:

1. Diagnose it from your own terminal — `kubectl -n t09 get events
   --sort-by=.lastTimestamp`, `kubectl -n t09 describe pod <name>`, and
   for `pod-e` also `kubectl -n t09 describe pvc zoo-data` and `kubectl
   get storageclass`. Each pod is failing for a genuinely different
   scheduler reason; don't assume they're all the same problem restated
   five times.
2. Fill in that pod's section in `DIAGNOSIS.md`: quote the exact symptom
   text you saw, state the root cause in your own words, and explain why
   your fix addresses it. Write these from what you actually observed —
   the validator checks each section for real scheduler vocabulary
   (`FailedScheduling`, `Insufficient`, `affinity`, `taint`, `toleration`,
   `unbound`, `storage class`, ...), not generic Kubernetes-troubleshooting
   prose that could apply to anything.
3. Write a corrected manifest in `fixes/<name>.yaml` — same Pod name, same
   container image, that actually reaches `Running`/`Ready` once applied.
   `fixes/pod-e.yaml` also needs a corrected `zoo-data` PersistentVolumeClaim
   (same name, still mounted by `pod-e` at the same path).

One constraint that applies to `pod-d` specifically: the fix is **not**
"remove whatever's stopping it from scheduling." `pod-d` must still end up
running on `sandbox20-worker2` specifically, with the quarantine taint
still on that node. The fix is something you *add* to the pod spec, not
something you delete — dropping the node constraint, or somehow getting
the taint removed, does not count even if the pod happens to go Running
some other way.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t09`, recreated fresh, deleted at the end
whether you pass or fail):

1. Runs the equivalent of `given/setup.sh` itself — retaints
   `sandbox20-worker2`, applies the zoo — and first confirms the fixture
   actually reproduces the expected `Pending` signature per pod (a
   non-vacuous check: if this step fails, the fixture itself is broken,
   not your fix).
2. Deletes the five original pods and the PVC, applies everything in
   `fixes/`, and waits for all five pods to reach `Running` with
   `Ready: True`.
3. For `pod-d` specifically: checks it landed on `sandbox20-worker2`
   (`spec.nodeName`), that its `nodeSelector` still pins
   `kubernetes.io/hostname: sandbox20-worker2`, that it carries a
   toleration matching `s20-t09/quarantine:NoSchedule`, and that the taint
   is still present on the node. Any of those missing fails validation
   even if the pod is somehow Running.
4. For `pod-e`: checks the `zoo-data` PVC is `Bound` and still mounted by
   `pod-e`.
5. Checks `DIAGNOSIS.md` has all five sections filled in with enough
   detail and grounded in real scheduler vocabulary, not placeholders.

The quarantine taint is removed from `sandbox20-worker2` and namespace
`t09` is deleted at the end regardless of outcome — you don't need to
clean either up by hand.

## Estimated evenings

1

## Topics to read up on

- Scheduler predicates and the `FailedScheduling` event: what
  `kubectl get events` shows you when a pod can't be placed, and how to
  read the aggregated message for *which* predicate rejected *which*
  nodes.
- Node labels and `nodeSelector` — how a pod requests a node by label,
  and what happens when no node in the cluster carries the label at all
  versus carrying a different value.
- Node affinity (`requiredDuringSchedulingIgnoredDuringExecution` vs.
  `preferredDuringSchedulingIgnoredDuringExecution`) and how it differs
  from a plain `nodeSelector` in expressiveness.
- Taints and tolerations — the three effects (`NoSchedule`,
  `PreferNoSchedule`, `NoExecute`) and why a toleration doesn't *attract*
  a pod to a tainted node, only permits it to land there if something
  else (a `nodeSelector`, an affinity rule) already sends it that way.
- PVC binding and `StorageClass` — `WaitForFirstConsumer` vs. immediate
  binding, what `kubectl get storageclass` tells you about what's
  actually available in a given cluster, and what a PVC referencing a
  nonexistent `storageClassName` looks like in events.
- QoS and resource `requests` — what "Insufficient cpu" in a
  `FailedScheduling` message means about the numbers you asked for versus
  what any single node in the cluster actually has to offer.
