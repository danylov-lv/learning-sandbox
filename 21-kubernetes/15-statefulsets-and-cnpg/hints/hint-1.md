# Hint 1

A Deployment's pods are anonymous and interchangeable: `deploy-abc123`
dies, `deploy-xyz789` takes its place, and nothing anywhere cares that
the name changed — the Service selector matches on labels, not on a
specific pod name, and every replica was running from the same image
with no local state that mattered.

A `StatefulSet` (and CNPG's `Cluster`, which manages its pods the same
way under the hood) gives up that anonymity on purpose, because for a
database the *identity* of a replica is data, not decoration:

- Pods get stable, predictable names/ordinals (`pg-cluster-1`,
  `pg-cluster-2`, `pg-cluster-3` for CNPG, or `<name>-0`, `<name>-1`,
  ... for a hand-rolled StatefulSet) instead of a random suffix.
- Each one gets its **own** PersistentVolumeClaim, created from a
  template, not one PVC shared across replicas. When a specific pod is
  deleted and recreated, it comes back and reattaches to *its own*
  PVC — the same data it had before, not empty storage and not another
  replica's data.
- Startup/scale-down happens in order (ordinal 0 before 1 before 2, and
  the reverse on the way down for a plain StatefulSet) rather than all
  at once, because a fresh replica about to start streaming replication
  needs the ones before it to already be functioning.

This is exactly why "just run Postgres in a Deployment" doesn't work:
scale a Deployment to 3 replicas and you get 3 pods that all think
they're independent, all trying to write to the same (or to
uninitialized, empty) storage, with no coordination about who's allowed
to accept writes. A `Cluster` CR (or a StatefulSet you configured
correctly yourself) is what makes "3 replicas of a database" mean "1
primary + 2 standbys that know their place," not "3 uncoordinated
copies."
