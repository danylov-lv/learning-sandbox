# 22 -- Operator Pattern: a kopf ScrapeJob Operator

## Backstory

Every earlier task in this module had you talk to Kubernetes: write a
manifest, apply it, watch it converge. This one flips the relationship --
you write something that IS part of Kubernetes' own control loop. A
`ScrapeJob` custom resource shows up; your code notices, and makes the
cluster match what it says. That's every controller in Kubernetes,
including the ones you've been relying on without a second thought all
module (the Deployment controller turning `spec.replicas` into actual
Pods is the exact same pattern, just written in Go and shipped inside
`kube-controller-manager`). Building one small, ugly version yourself is
the fastest way to stop treating that as magic.

The whole platform is one CRD (`ScrapeJob`) plus one Python file
(`operator.py`) built on [`kopf`](https://kopf.readthedocs.io/), a
framework that turns "watch this resource type, run my function on
create/update/delete" into a decorator. Your `ScrapeJob` describes a pool
of scrape workers (replica count, image, simulated per-item processing
time); your operator's job is to keep a worker Deployment in sync with
whatever the current `ScrapeJob` says, and to clean it up the moment the
`ScrapeJob` is deleted.

This is a multi-evening capstone with three checkpoints: get create
working first (CP1), then update-reconcile and delete-cleanup (CP2), then
defend the design in writing and prove both earlier checkpoints still pass
(CP3).

## What's given

- `src/crd.yaml` -- a `TODO(you)` skeleton: the right `apiVersion`/`kind`/
  `metadata.name`, an empty `spec: {}` for you to fill in against the
  schema contract below.
- `src/operator.py` -- imports, the CRD's group/version/plural as
  constants, the two labels every child Deployment must carry, and a
  naming helper. All three handler bodies (`on_create`, `on_update`,
  `on_delete`) raise `NotImplementedError` -- that's the assignment.
- `tests/_opharness.py` -- NOT part of the assignment. Shared plumbing the
  three checkpoint validators use to run your `operator.py` as a real
  subprocess against the live cluster and clean up afterwards. Read it if
  you're curious how the validator drives your operator; you never need
  to edit or run it directly.
- `DESIGN.md` -- an unfilled template with the five sections CP3 checks.
- `hints/` -- three files, escalating from direction to concrete approach
  (no ready-to-paste operator code in any of them -- writing the handlers
  is the point).

## Schema contract

State up front, because none of it should be a surprise buried in a
validator:

- **CRD identity**: group `sandbox20.dev`, version `v1`, kind `ScrapeJob`,
  plural `scrapejobs`, singular `scrapejob`, namespaced.
- **`spec` fields** (all three, exactly these names):
  - `replicas` -- integer, minimum 1, default 1
  - `image` -- string, default `sandbox20-app:1.0`
  - `processMs` -- integer, minimum 1, default 100
- **Child Deployment labels** -- every worker Deployment your operator
  creates must carry, on its own `metadata.labels` (the validators select
  Deployments this way, not by name -- name the Deployment whatever you
  like):
  - `app.kubernetes.io/managed-by: scrapejob-operator`
  - `scrapejob-name: <the ScrapeJob's metadata.name>`
- **Container**: the worker container runs the given `spec.image` with
  env var `PROCESS_MS` set from `spec.processMs` (the fixture app's
  `WORK_MODE=server` default is fine -- this task is about the operator,
  not the app; you don't need `WORK_MODE=consumer`/a live queue).
- **Replica count**: the Deployment's `spec.replicas` tracks
  `spec.replicas` on the CR, both at creation and after an update.
- **Deletion**: deleting the `ScrapeJob` CR must result in the child
  Deployment being removed, explicitly, by your `on_delete` handler --
  not left to owner-reference garbage collection alone (set the owner
  reference too via `kopf.adopt`, but don't rely on GC's timing for the
  validator's bounded wait).

## What's required

Write `src/crd.yaml`'s `spec` and all three handler bodies in
`src/operator.py`. The validators run your operator for you -- there is no
separate "run the operator yourself" step; `uv run python tests/validate_cp1.py`
starts it, drives it, and stops it.

### CP1 -- create (`validate_cp1.py`)

Applies your CRD, starts your operator, applies one `ScrapeJob` CR
(`replicas: 2`), and asserts exactly one child Deployment appears carrying
the label contract above, reaching 2/2 ready replicas, and that the
operator's own log shows a successful create reconcile for that CR.

### CP2 -- update + delete (`validate_cp2.py`)

Applies a `ScrapeJob` (`replicas: 1`), waits for the child Deployment,
then patches the CR to `replicas: 3` and asserts the SAME Deployment
object (its `uid` doesn't change -- your `on_update` must patch the
existing Deployment, not delete and recreate it) reaches 3/3 ready
replicas. Then deletes the CR and asserts the child Deployment disappears
within a bounded wait. Finally greps the operator's log for kopf's own
reconcile-summary lines confirming both the update and the delete were
processed successfully.

### CP3 -- design review (`validate_cp3.py`)

Fill in every section of `DESIGN.md`, grounded in the operator you
actually wrote (see `hints/hint-3.md` if "grounded" is unclear). The
validator then re-runs `validate_cp1.py` and, if that passes,
`validate_cp2.py` as real subprocesses -- both must still exit 0.

## Completion criteria

From this task directory (needs the `sandbox20` kind cluster up -- `bash
../scripts/cluster-up.sh` from the module root if it isn't, and the
fixture images loaded via `../scripts/build-images.sh`):

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

Each prints exactly one `PASSED` (with a trailing detail) on success, or
one `NOT PASSED: <reason>` and exits 1 on failure -- no raw tracebacks.
Every checkpoint terminates its operator subprocess and deletes namespace
`t22` and the `scrapejobs.sandbox20.dev` CRD whether it passes or fails,
so re-running any of them is safe.

## Estimated evenings

2-3

## Topics to read up on

- CustomResourceDefinitions -- how a CRD teaches the API server a new
  resource type, and what `additionalPrinterColumns`/OpenAPI schema
  validation/defaulting buys you for free
- The operator / controller pattern -- a process that watches one kind of
  object and drives the cluster's actual state toward what it declares,
  same shape whether it's `kube-controller-manager` or your `operator.py`
- Reconcile loops and **level-triggered** vs. edge-triggered reconciliation
  -- why "handle this one delta" is the wrong mental model and "make
  reality match the whole current spec, however you got the notification"
  is the right one
- Owner references and cascading (garbage-collector) deletion -- what
  `kopf.adopt` sets up, and why a real operator still often deletes
  children explicitly rather than trusting GC's timing
- Idempotency of reconcile handlers -- what happens if `on_create` fires
  twice for the same object (operator restart, at-least-once delivery),
  and why handlers need to tolerate that
- kopf's handler model specifically: `@kopf.on.create/update/delete`,
  the finalizer it adds automatically so delete can be intercepted, and
  what its own log lines (`Creation/Updating/Deletion is processed: N
  succeeded`) tell you about a reconcile that actually ran

## Off-limits

`.authoring/design.md` (at the module root) holds this module's full
infrastructure contract, including this task's verification approach in
more explicit detail -- spoilers. Don't read it before finishing this
task.
