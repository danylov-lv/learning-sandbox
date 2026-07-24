# Authoring notes -- 15-statefulsets-and-cnpg

Owning task for the **CloudNativePG operator** (cluster-global install,
`scripts/install.sh` + `uninstall.sh`). Later tasks assume it stays
installed in `cnpg-system`.

## Versions pinned (verified live against this cluster, k8s v1.32.2)

- CNPG operator **1.29.2**, applied from
  `https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.29/releases/cnpg-1.29.2.yaml`;
  operator Deployment `cnpg-controller-manager` in `cnpg-system`, waited
  Ready via `rollout status --timeout=180s`. Idempotent/re-runnable.
- Postgres image `ghcr.io/cloudnative-pg/postgresql:17.6`, `instances: 3`,
  `storage.storageClass: standard` (the kind local-path default).

## Task / grading

Learner writes `src/cluster.yaml` (a CNPG `Cluster` CR). Validator applies
it into `t15`, waits (bounded) for `status.readyInstances == instances` and
a healthy phase, identifies the current primary
(`status.currentPrimary` / label `cnpg.io/instanceRole=primary`),
force-deletes the primary pod, and asserts a NEW primary is elected and the
cluster returns fully-ready within a bounded `wait_until`. README + a gated
NOTES reflection cover StatefulSets-vs-Deployments / why-DBs-on-k8s-hurt.

## Verified

Stock (unfilled `src/cluster.yaml` stub) fails cleanly:
`NOT PASSED: kubectl apply -f cluster.yaml failed: error: no objects passed
to apply`, exit 1, one line.

Reference pass-path (3-instance cluster bring-up + forced-primary-deletion
failover recovery) was proven live by the authoring subagent with a
throwaway `Cluster` CR, then the stub was reverted byte-identical (sha
confirmed) -- no reference solution committed. Orchestrator re-confirmed the
reverted stub + clean stock-fail this session; `cnpg-controller-manager`
1/1 Available; namespace `t15` deleted (operator left installed).

NOTE: bringing up a 3-instance Postgres cluster and completing a failover
takes a few minutes -- validator uses generous bounded waits, no
absolute wall-clock gate.
