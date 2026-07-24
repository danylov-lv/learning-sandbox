# 12 — Services and DNS debugging

## Backstory

A routing migration touched every Service in front of `catalog-backend`.
The backend itself is fine -- its pods start, pass their readiness probe,
and would happily answer any request that reached them. But three
different callers, going through three different Services, all report the
same thing: nothing gets through. Same healthy backend, three different
Service-level ways to break the path to it, and you get to find each one.

## What's given

- `given/broken.yaml` -- applied fresh into namespace `t12` by
  `given/setup.sh` (and independently by `tests/validate.py` itself, so the
  validator never depends on you having run `setup.sh` first):
  - a `Deployment` (`catalog-backend`, image `sandbox20-app:1.0`, 2
    replicas) that is healthy. Its readiness probe hits the port the
    container actually listens on. **This Deployment is not broken and has
    no fix file** -- don't waste time looking for a bug in it.
  - three `Service`s, all meant to route ordinary traffic to
    `catalog-backend` on port 80: `catalog`, `catalog-batch`, and
    `catalog-peer`. Each has exactly one independent defect.
- `given/setup.sh` -- resets namespace `t12` and applies the fixture. Handy
  for poking around by hand; the validator doesn't need it.

**Do not edit `given/broken.yaml`.** Your fixes live in
`src/catalog-fix.yaml`, `src/catalog-batch-fix.yaml`, and
`src/catalog-peer-fix.yaml` -- `kubectl apply` with those re-patches the
Service objects the fixture defines.

## What's required

Diagnose each Service on its own terms -- don't assume they share a root
cause just because they were all touched by the same migration. For each
one, start from evidence (`kubectl get endpoints`, `kubectl describe svc`,
an in-cluster DNS lookup), not from guessing.

**1. `catalog`** -- callers get a fast connection failure. Check
`kubectl get endpoints catalog`. What you find there tells you immediately
which of "no Endpoints" vs "Endpoints exist but something else is wrong"
you're looking at.

**2. `catalog-batch`** -- `kubectl get endpoints catalog-batch` shows real
pod IPs, so the selector is fine. Look at *which port* those Endpoints
advertise, and compare it against the port `catalog-backend`'s container
actually listens on (its `containerPort`, or its own readiness probe --
that one already works, so it's a reliable source of truth for the real
port).

**3. `catalog-peer`** -- `kubectl describe svc catalog-peer` and compare it
against `kubectl describe svc catalog` (once you've fixed that one).
One of them has a stable `IP:` field; the other doesn't. Read up on what a
headless Service (`clusterIP: None`) actually does to DNS resolution and to
kube-proxy's routing before you decide this one's fix.

Each `src/*-fix.yaml` is currently a `TODO(you)` skeleton comment with no
resource in it -- it fails cleanly (nothing to apply) rather than with a
YAML parse error. Read the comment block in each before writing: they call
out real `kubectl apply` gotchas (three-way merge silently dropping fields
you don't re-list; `spec.clusterIP` being immutable once a Service exists)
that will bite you if you don't plan around them.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t12`, recreated on every run):

1. Applies `given/broken.yaml` and confirms each of the three symptoms this
   README claims is real (`catalog` has zero Endpoints; `catalog-batch` has
   Endpoints but on the wrong port; `catalog-peer` is headless) before
   giving any credit.
2. Runs a probe Job inside `t12` that resolves each Service's DNS name
   (`<svc>.t12.svc.cluster.local`) and curls it on port 80, and confirms
   this probe actually fails against the seeded, unfixed state.
3. Deletes the three broken Services and applies your
   `src/catalog-fix.yaml`, `src/catalog-batch-fix.yaml`, and
   `src/catalog-peer-fix.yaml` (deletion first because `catalog-peer`'s fix
   needs to flip `spec.clusterIP`, which `kubectl apply`/`patch` cannot do
   in place on an existing Service).
4. Checks the specific field each fix was responsible for (`catalog` has
   Endpoints again; `catalog-batch`'s `targetPort` matches the real
   container port; `catalog-peer` has a real, non-`None` `clusterIP`).
5. Reruns the same probe Job and asserts all three targets now return a
   `200` from `/`.

Namespace `t12` is deleted at the end whether you pass or fail.

## Estimated evenings

1

## Topics to read up on

- Service types: `ClusterIP` (the default, a stable virtual IP kube-proxy
  load-balances to), headless (`clusterIP: None`), `NodePort`
- Selectors and `Endpoints`/`EndpointSlice` -- how a Service decides which
  pods back it, and what it looks like when nothing matches
- kube-proxy basics -- how a `ClusterIP` Service's port gets translated to
  a pod's real port, and why that translation doesn't happen for headless
  Services
- Cluster DNS / CoreDNS: `<svc>.<namespace>.svc.cluster.local`, and how the
  A record it returns differs for a normal `ClusterIP` Service (the
  Service's own IP) versus a headless one (the backing pods' IPs directly)
- `targetPort` vs `port` -- which one a client cares about, which one has
  to match something real on the pod, and how `kubectl get endpoints` shows
  you the ground truth cheaply
- Why `spec.clusterIP` is immutable on an existing Service, and what that
  means for how you apply a fix that needs to change it

## Off-limits

`.authoring/design.md` and `.authoring/notes-t12.md` are spoiler-level
design material for this module -- don't read them before you're done with
this task.
