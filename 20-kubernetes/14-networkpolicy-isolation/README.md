# 14 — NetworkPolicy isolation

## Backstory

`worker` is a scrape-style consumer: it drains jobs off `queue` and writes
its results out through `target`. That's the whole job. It has no business
talking to anything else in the cluster -- and if it's ever compromised
(a malicious dependency, a bad deploy, whatever), you don't want it able to
pivot sideways to some other internal service just because nothing stopped
it. Right now, nothing stops it: every pod in this cluster can reach every
other pod, in every namespace, on every port. Your job is to change that for
`worker` specifically, without breaking the one thing it's actually supposed
to do.

## What's given

`given/setup.sh` applies this topology into namespace `t14` (plus one piece
in a second namespace, `t14-external`):

- `queue` -- a redis instance (`given/queue.yaml`). `worker`'s legitimate
  queue backend, listening on `6379`.
- `target` -- a plain fixture app (`given/target.yaml`), `worker`'s
  legitimate, allowed scrape target, listening on `8080` (exposed through
  its Service on port `80`).
- `worker` -- the component you're isolating (`given/worker.yaml`),
  `WORK_MODE=consumer` pointed at `queue`. Labeled `app: worker`.
- `decoy` -- another fixture app (`given/decoy.yaml`), same namespace
  (`t14`) as `worker`, same shape as `target`, but **not** one of worker's
  allowed targets. Stands in for "some other internal service that happens
  to share a namespace with you".
- `outsider` -- one more fixture app (`given/outsider.yaml`), but applied
  into a **different** namespace, `t14-external`. Stands in for "some other
  team's service elsewhere in the cluster".

Right now, with no `NetworkPolicy` in play at all, `worker` can reach
`decoy` and `outsider` just as easily as `queue` and `target` -- and `decoy`
and `outsider` can reach `worker` right back. That's the baseline you're
locking down.

`given/setup.sh` resets both namespaces and reapplies everything; handy for
poking around by hand. `tests/validate.py` seeds the same topology itself,
independently, so it never depends on you having run `setup.sh` first.

## What's required

Write `src/networkpolicy.yaml` -- currently a `TODO(you)` skeleton comment
block with no resource in it, so it fails cleanly (nothing to apply, not a
YAML parse error) until you fill it in.

Your `NetworkPolicy` (or policies -- one is enough, but nothing stops you
from splitting ingress and egress into two if that's clearer to you) must,
scoped to `worker`'s pods only (`podSelector: {matchLabels: {app: worker}}`,
**not** the whole namespace):

1. **Deny all ingress** -- nothing should be able to open a connection to
   `worker`. It doesn't serve traffic to anything; there's no legitimate
   reason for `ingress` to allow anything at all.
2. **Allow egress to `queue`**, on the port it actually listens on.
3. **Allow egress to `target`**, on the port it actually listens on (read
   the "ports" gotcha in `src/networkpolicy.yaml`'s comment block before you
   guess this one -- it isn't the Service's port).
4. **Allow egress for DNS** -- `worker` resolves `queue` and `target` by
   Service name before it can connect to either. If you forget to allow
   egress to CoreDNS, you'll block the very traffic you meant to allow.
5. **Deny everything else** -- by default. A `NetworkPolicy` with
   `policyTypes: [Ingress, Egress]` denies-by-default anything not matched
   by an explicit rule, so as long as you don't add a rule for `decoy` or
   `outsider`, they're already denied. You don't need (and shouldn't add) an
   explicit deny rule for them.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespaces `t14` and `t14-external`, both recreated on every
run):

1. Seeds the topology above and waits for every Deployment to roll out.
2. Applies your `src/networkpolicy.yaml` (a no-op if it's still the
   unfilled stub).
3. Runs six one-shot probe Jobs -- each one impersonates a component by
   carrying its exact labels (`app: worker`, `app: decoy`, `app: outsider`),
   so whatever `podSelector` your policy actually uses is exactly what gets
   exercised -- and asserts:
   - `worker -> queue` **succeeds**
   - `worker -> target` **succeeds**
   - `worker -> decoy` **is blocked**
   - `worker -> outsider` (cross-namespace) **is blocked**
   - `decoy -> worker` **is blocked**
   - `outsider -> worker` (cross-namespace) **is blocked**

A mismatch anywhere -- expected reachable but blocked, or expected blocked
but reachable -- is a single `NOT PASSED` line naming exactly which leg
failed. With nothing written yet, every negative check above currently
*succeeds* (the connection goes through when it shouldn't), so the very
first one the validator checks is what fails you -- a genuine test of
policy enforcement, not a placeholder-text check. (This is also why this
task depends on Calico, which actually enforces `NetworkPolicy` -- kind's
default CNI would silently let all six probes "pass" regardless of what you
wrote.)

Both namespaces are deleted at the end whether you pass or fail.

## Estimated evenings

1

## Topics to read up on

- `NetworkPolicy` ingress vs. egress, and `policyTypes` -- what "no policy"
  vs. "a policy with an empty `ingress: []`" actually mean for a pod
- Default-deny: a `NetworkPolicy` selecting a pod switches that pod's
  ingress/egress from "everything allowed" to "only what's explicitly
  allowed, for whichever `policyTypes` you listed" -- and *only* for pods it
  selects, not the whole namespace
- `podSelector` vs. `namespaceSelector` in an `ingress`/`egress` rule's `to`/
  `from`, and how to combine them to mean "this pod, in that namespace"
- Why the CNI matters: `NetworkPolicy` objects are inert metadata unless
  something (Calico, Cilium, etc.) actually enforces them -- kindnet
  (kind's default) does not
- The DNS-egress gotcha: an egress-locked-down pod needs an explicit allow
  rule for DNS (typically to CoreDNS in `kube-system`, UDP+TCP port `53`)
  or it can't resolve any Service name at all, including the ones you meant
  to allow

## Off-limits

`.authoring/design.md` and `.authoring/notes-t14.md` are spoiler-level
design material for this module -- don't read them before you're done with
this task.
