# Authoring notes -- 20-pdb-vs-node-drains

The ONLY task allowed to cordon/drain nodes. Authored inline by the
orchestrator after the delegated subagent hit a session limit mid-write
(it had left only an empty dir skeleton + a stale `observe-spread.sh`
referencing a different deployment name `scraper-fleet`; removed).

## Design

- Fixture: `web` Deployment, 4 replicas, `sandbox20-app:1.0`, serving
  `/readyz`. Soft `topologySpreadConstraints` (maxSkew 1,
  `whenUnsatisfiable: ScheduleAnyway`, key `kubernetes.io/hostname`) so it
  starts 2-and-2 across the two workers but CAN pile onto the surviving
  worker while the other is cordoned -- a HARD spread would deadlock the
  drain. Control-plane's default NoSchedule taint keeps all 4 on workers.
- Learner deliverable: `src/pdb.yaml`, a PodDisruptionBudget. Contract
  (stated in README): select `app: web`, keep >= 3 of 4 available
  (minAvailable: 3 == maxUnavailable: 1). Too weak (0/1/2) and too strict
  (4, blocks the drain forever) both rejected.

## Validator (tests/validate.py)

`require_cluster()`; seed + rollout; assert real 2-worker spread (non-vacuous
fixture); apply the PDB (unfilled stub -> `no objects passed to apply` ->
NOT PASSED). Then read PDB `.status`: reject `expectedPods<4`/`currentHealthy<4`
(selector miss), `desiredHealthy<3` (too weak), `desiredHealthy>=4` (too
strict) -- this is the anti-cheat against a degenerate budget, keyed on the
API-computed desiredHealthy so both minAvailable:3 and maxUnavailable:1 pass.
Then `kubectl drain <worker> --pod-selector app=web --ignore-daemonsets
--delete-emptydir-data --timeout=180s` while a daemon thread polls
`deployment.status.readyReplicas` and records the minimum; assert min >=
desiredHealthy, drain completes, drained node ends with no web pods, fleet
back to 4. **`--pod-selector app=web` is load-bearing**: it evicts ONLY web
pods, leaving the cluster-global platform (Argo CD, CNPG operator, RabbitMQ,
Prometheus) untouched on the cordoned node -- much less disruptive and
avoids waiting on other components' rescheduling.

`finally`: uncordon EVERY node (idempotent) + delete t20 -- runs even on
failure because `guarded` re-raises SystemExit. Startup does a
`delete_ns(t20, wait=True)` before recreating, so back-to-back runs don't
race a still-Terminating namespace (found + fixed live: the first
reference-run failed with "namespace ... is being terminated" from the
prior run's async finally-delete).

## Verified live (orchestrator)

- Stock: `NOT PASSED: kubectl apply -f src/pdb.yaml failed: error: no
  objects passed to apply`, exit 1, one line; nodes uncordoned afterward.
- Reference (`minAvailable: 3`): `PASSED: PDB held web >= 3/4 Ready through
  a drain of sandbox20-worker (minimum observed 3); fleet recovered to 4`,
  exit 0. Stub reverted byte-identical (sha256 matched); re-ran stock after
  revert -> same clean fail. All 3 nodes Ready + schedulable at the end.
