# Hint 3

What to actually watch while the failover happens (both when you trigger
it by hand and when the validator does it):

- `kubectl -n t15 get cluster pg-cluster -o
  jsonpath='{.status.currentPrimary}'` — the name of whichever pod is
  primary *right now*. This is the single field that changes value when
  a failover happens; it does not change name-format or shape, just
  which pod it points at.
- `kubectl -n t15 get pods -l cnpg.io/instanceRole=primary` — CNPG keeps
  this label in sync with `status.currentPrimary`, so it's a second way
  to answer "which pod is primary" without trusting the status field
  alone. The other two pods carry
  `cnpg.io/instanceRole=replica` instead.
- `kubectl -n t15 get cluster pg-cluster -o
  jsonpath='{.status.readyInstances}'` vs. `.status.instances` — the
  cluster is only "fully healthy" when these are equal (and equal to
  the `spec.instances` you asked for). Right after a force-delete
  they'll briefly disagree — that's expected, not a bug — and should
  converge back to equal within the bounded wait.

The sequence after a force-delete of the primary, roughly: CNPG notices
the primary pod is gone, evaluates which surviving replica has the most
caught-up replication state, promotes that one (this is the "new
`currentPrimary`" you're waiting for), and *separately* recreates the
deleted pod as a fresh replica that reattaches to its own existing PVC
and starts streaming from whichever pod is primary now. Both things need
to finish — new primary elected, **and** the recreated pod back and
caught up — before `readyInstances` returns to `instances`. Don't be
surprised if the pod that comes back keeps its old name (`pg-cluster-2`
stays `pg-cluster-2`) but its *role* is now `replica` even though it used
to be `primary` — that's the stable-identity-with-changing-role
behavior this whole task is about.

If the wait times out with `readyInstances` stuck below `instances`,
`kubectl -n t15 describe pod <name>` and `kubectl -n t15 logs
<name> -c postgres` on whichever instance isn't ready are the first
places to look — a common cause in a resource-constrained lab cluster is
the recreated pod simply needing more time to pull the image again or to
finish `pg_basebackup`, which the bounded wait already accounts for
generously, not a sign that something is actually broken.
