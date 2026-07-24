# 20 -- PDB vs node drains

## Backstory

A worker node needs maintenance -- a kernel patch, a kubelet upgrade, a
hardware swap. The way you take a node out of service gracefully is
`kubectl drain`: it cordons the node (no new pods) and evicts the pods
already on it so they reschedule elsewhere. But eviction is a *voluntary*
disruption, and voluntary disruptions respect a **PodDisruptionBudget**. Get
the PDB right and the drain rolls your pods off one at a time, never taking
the service below a safe replica count. Get it wrong -- no budget, or a
budget that protects nothing -- and the drain can yank every replica off the
node at once; get it *too* strict and the drain blocks forever and the node
never drains at all.

You have a `web` fleet of 4 replicas spread across the two worker nodes.
Your job is the PDB that lets a node be drained safely.

> **This task drains a real node.** The validator cordons one worker,
> evicts the `web` pods off it, and then **uncordons every node again at the
> end, whether you pass or fail**. It only ever evicts pods labelled
> `app: web` (via `kubectl drain --pod-selector`), so the rest of the
> cluster's workloads stay put. This is the only task in the module allowed
> to touch node scheduling.

## What's given

`given/setup.sh` applies `given/deployment.yaml` into namespace `t20`: the
`web` Deployment, 4 replicas, soft-spread 2-and-2 across `sandbox20-worker`
and `sandbox20-worker2` (a soft spread so the replicas can pile onto the
surviving worker while the other is cordoned). `tests/validate.py` seeds the
same thing itself, so you don't have to run `setup.sh` first.

Look at the spread before you start:

```bash
kubectl --context kind-sandbox20 -n t20 get pods -o wide
```

## What's required

Write `src/pdb.yaml` -- a `PodDisruptionBudget` for the `web` pods. It must:

1. **Select the web pods** (`selector.matchLabels.app: web`). A PDB that
   selects nothing protects nothing.
2. **Keep at least 3 of the 4 replicas available** at all times:
   `minAvailable: 3`, or equivalently `maxUnavailable: 1` (a percentage that
   works out the same, like `maxUnavailable: 25%`, is fine).
3. Not be **too weak** (`minAvailable: 0/1/2`) -- that wouldn't hold
   availability up through the drain.
4. Not be **too strict** (`minAvailable: 4`, equal to the replica count) --
   that allows zero voluntary disruptions, so the node can never finish
   draining. Leave exactly one disruption of headroom.

The stub in `src/pdb.yaml` is a `TODO(you)` comment block with no resource
in it, so it fails cleanly (nothing to apply) until you fill it in.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator seeds the fleet, applies your PDB, checks it actually selects
the web pods and has the right amount of headroom, then drains one worker's
web pods while watching that Ready replicas never dip below your budget's
`desiredHealthy`. It asserts the drain completes, the drained node ends up
with no web pods, and the fleet returns to 4 Ready -- then uncordons every
node and deletes `t20`.

## Estimated evenings

1

## Topics to read up on

- `PodDisruptionBudget`: `minAvailable` vs `maxUnavailable`, and how each
  maps to the API's `desiredHealthy`
- Voluntary vs involuntary disruptions -- a PDB only governs the voluntary
  ones (drains, rolling updates), not a node crashing
- `kubectl cordon` / `drain` / `uncordon`, the eviction API, and how the
  eviction API consults the PDB before removing each pod
- Why a `minAvailable` equal to the replica count deadlocks a drain, and how
  a soft `topologySpreadConstraint` (`ScheduleAnyway`) lets replacements
  land on the surviving node so the drain can proceed
- How a PDB interacts with rolling updates (the same budget is enforced
  there, which is why an over-strict PDB can also stall a rollout)

## Off-limits

`.authoring/design.md` and `.authoring/notes-t20.md` are spoiler-level
design material for this module -- don't read them before you're done.
