# 15 — StatefulSets, CloudNativePG, and a real failover

## Backstory

Everything so far has been stateless: a Deployment's pods are
interchangeable, any one of them can die and get replaced by an
identical twin, and nothing downstream needs to know or care which pod
answered a request. A database is the opposite of that. Each replica has
its own data on disk, replicas are not interchangeable (there is exactly
one primary at a time, and it matters which one), and replacing a dead
pod with "a fresh identical one" would mean replacing it with an *empty*
one — which is not a recovery, it's data loss.

That's why Kubernetes has a second workload controller, `StatefulSet`,
and why nobody hand-rolls one for Postgres in production: the mechanics
of "run a database well on Kubernetes" (stable identity, ordered
startup, per-replica storage, promoting a replica to primary without
losing committed transactions, doing all of that automatically when a
node dies at 3am) are a job for a purpose-built **operator**, not a bare
StatefulSet manifest. This task installs one — [CloudNativePG
(CNPG)](https://cloudnative-pg.io/) — brings up a real 3-instance
Postgres cluster through its `Cluster` custom resource, and then breaks
it on purpose to watch it heal.

## What's given

- `scripts/install.sh` — installs the CNPG operator (a **cluster-global**
  install, pinned to CNPG **1.29.2**, into namespace `cnpg-system`). This
  task owns that install for the rest of the module: run it once, leave
  it installed, and every later task that happens to reuse this cluster
  can assume the operator is already there. Re-running it is safe
  (idempotent apply + a rollout wait that returns immediately if already
  Ready).
- `scripts/uninstall.sh` — the matching teardown (removes the operator
  and its CRDs). You should not need this to complete the task; it
  exists for fully decommissioning the cluster-global install, and it
  refuses to run while any `Cluster` object still exists anywhere on the
  cluster.
- `src/cluster.yaml` — a `TODO(you)` stub. `kubectl apply -f
  src/cluster.yaml` against it applies nothing (no object, no error)
  until you replace it with a real `Cluster` custom resource.

## What's required

1. Run `bash scripts/install.sh` once. Confirm
   `kubectl --context kind-sandbox20 -n cnpg-system get deployment
   cnpg-controller-manager` shows it Available before moving on.

2. Write `src/cluster.yaml`: a CNPG `Cluster` custom resource (this is a
   CRD the operator registers, not a builtin object) with:
   - `metadata.name: pg-cluster`
   - `spec.instances: 3` — one primary, two streaming-replica standbys.
   - `spec.imageName: ghcr.io/cloudnative-pg/postgresql:17.6` — this
     exact tag was verified to pull cleanly against this cluster's
     containerd; CNPG ships a whole catalog of Postgres versions under
     `ghcr.io/cloudnative-pg/postgresql`, this is simply a specific,
     working pin.
   - `spec.storage.size` — your choice (`1Gi` is plenty for this lab)
     and `spec.storage.storageClass: standard` — this cluster's default
     `StorageClass`, backed by `local-path-provisioner`. CNPG creates
     **one PVC per instance** (not one shared volume) — that's the
     "PVC-per-replica" half of the StatefulSet story, and it's why a
     replica that gets rescheduled comes back with *its own* data
     rather than someone else's.

   Apply it into namespace `t15` and watch it come up:
   `kubectl --context kind-sandbox20 -n t15 get cluster pg-cluster` and
   `kubectl --context kind-sandbox20 -n t15 get pods -w`. Bringing up
   three fresh Postgres instances (image pull + `initdb` on the first
   one + `pg_basebackup` cloning for the other two) takes a few minutes
   the first time — that's expected, not a hang.

3. Once the cluster reports all three instances ready, trigger a
   **simulated failover** yourself, by hand, before the validator does
   it again for real: find the current primary
   (`kubectl -n t15 get cluster pg-cluster -o
   jsonpath='{.status.currentPrimary}'`, or `kubectl -n t15 get pods -l
   cnpg.io/instanceRole=primary`) and force-delete that pod
   (`kubectl -n t15 delete pod <primary> --grace-period=0 --force`).
   Watch what happens to `status.currentPrimary` and `kubectl -n t15 get
   pods` over the next minute or two. This is the whole point of the
   operator: nobody told it which replica to promote, it decided based
   on replication state, and the deleted pod's *name* comes back once
   its PVC is reattached and it rejoins as a replica — because CNPG
   manages per-instance identity the same way a StatefulSet would, not
   by handing out a fresh, anonymous replacement.

4. Write up what you observed in `NOTES.md` — see "Completion criteria"
   below for exactly what's graded there.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t15`, recreated fresh, deleted at the end
whether you pass or fail — the CNPG operator itself is **not** touched):

1. Confirms the CNPG operator is installed and Ready (tells you to run
   `scripts/install.sh` if not).
2. Applies `src/cluster.yaml` and checks the `Cluster` object's own spec:
   `instances: 3`, an image under `ghcr.io/cloudnative-pg/postgresql`,
   and `storage.size`/`storage.storageClass` set as contracted above.
3. Waits (bounded, generous — cold image pulls and initial
   `pg_basebackup` cloning take real time) for the Cluster's own status
   to report `readyInstances == instances == 3` and a `currentPrimary`.
4. Identifies the current primary pod from `status.currentPrimary`
   (cross-checked against the pod's own `cnpg.io/instanceRole=primary`
   label), **force-deletes it**, and waits (bounded) for CNPG to elect a
   *different* pod as the new primary and for the cluster to return to
   `3/3` ready — proof of an actual failover, not just that the fields
   are set correctly on paper.
5. Checks `NOTES.md`: three sections (`StatefulSets vs Deployments`,
   `Failover observations`, `Why databases on Kubernetes are hard`) each
   filled in with your own observations, grounded in specific
   terminology (stable identity, per-replica PVCs, ordering, headless
   Services, quorum/failover) rather than restating the README.

## Estimated evenings

1-2

## Topics to read up on

- `StatefulSet`: stable, ordinal pod names (`-0`, `-1`, `-2`, ...),
  ordered startup/scale-down, and a `volumeClaimTemplate` giving each
  replica its own PVC instead of one shared volume.
- The headless `Service` (`clusterIP: None`) a `StatefulSet` needs for
  per-pod DNS (`<pod>.<service>.<namespace>.svc.cluster.local`) — how
  that differs from a normal `ClusterIP` Service load-balancing across
  interchangeable endpoints.
- Kubernetes **operators** and **CRDs**: why "a controller plus a custom
  resource that encodes domain knowledge" beats "a generic StatefulSet
  manifest" for anything with real operational logic (failover, backups,
  minor-version upgrades) behind it.
- CloudNativePG's architecture specifically: one primary + N streaming
  replicas, how it decides which replica to promote, and what
  `status.currentPrimary` / `status.readyInstances` / the
  `cnpg.io/instanceRole` pod label mean.
- Postgres streaming replication and quorum at a conceptual level — why
  losing the primary isn't automatically safe to recover from
  instantly, and what "how much committed data can we afford to lose"
  has to do with how many replicas must acknowledge a write.
- Why running stateful workloads (especially databases) on Kubernetes is
  considered hard: the mismatch between "pods are cattle, replace them
  freely" and "this pod's disk holds the only copy of some data," and
  why that mismatch is exactly what an operator like CNPG exists to
  paper over.
