# Authoring notes -- 03-jobs-cronjobs-and-resources

- Stub convention check: same as task 01 -- `src/job.yaml` and
  `src/cronjob.yaml` containing only `#` comment lines make `kubectl
  apply -f <file>` fail with `error: no objects passed to apply`
  (exit 1), no YAML parse error, no traceback.
- Resource comparison in the validator parses cpu/memory quantities into
  base units (millicores, bytes) rather than doing string equality --
  `50m` vs `0.05` cpu, or `64Mi` vs an equivalent byte count, should both
  be accepted as "50m"/"64Mi" even though the contract's README only
  shows the canonical `m`/`Mi` spelling. Kept the parser intentionally
  small (suffix table for cpu `m` and mem `Ki/Mi/Gi/K/M/G`) since this
  module's fixture app and every task only ever needs these forms.
- Parallelism-overlap proof: with `parallelism: 2`, `completions: 4`, and
  a `sleep(3)`-per-shard workload, the two pods in the first batch landed
  `status.startTime` seconds apart at worst and both terminated ~3s
  later -- overlap window observed live was a full 4 seconds
  (`2026-07-23T11:43:03 -> 2026-07-23T11:43:07`), nowhere near a close
  call. `sleep(3)` is plenty on this cluster (images already
  `kind load`ed, no pull latency) -- did not need to tune it up. Kept the
  README's wording as "sleep a few seconds" rather than hardcoding "3" as
  a requirement, since the overlap proof only needs *some* shared window,
  not a specific duration; the validator doesn't hardcode an expected
  sleep length anywhere, only checks structural fields, resources, QoS,
  succeeded count, and the overlap condition itself.
- QoS check: `requests` (`50m`/`64Mi`) strictly less than `limits`
  (`200m`/`128Mi`) on every resource, on the only container in the pod --
  confirmed live as `Burstable`, not `Guaranteed` (would need
  requests == limits on every resource) and not `BestEffort` (would need
  no requests/limits set at all).
- CronJob spawned-job discovery: filtered `kubectl get jobs -n t03` by
  `ownerReferences[].kind == CronJob` and `.name == scheduled-scrape`,
  explicitly excluding the `rescrape` Job by name -- both Job kinds live
  in the same namespace and list together. With `schedule: "* * * * *"`
  the first spawn showed up well inside the 75s budget in live testing
  (worker pod for the cron-spawned Job start lag was on the order of a
  few seconds past the scheduled minute boundary).
- `kubectl patch cronjob ... --type=merge -p '{"spec":{"suspend":true}}'`
  works cleanly against `batch/v1` CronJob; re-reading `spec.suspend`
  immediately after confirms it stuck. Did not attempt to observe actual
  history-limit pruning (would need several minutes of ticks
  accumulating) -- validator only re-asserts the *fields*
  (`successfulJobsHistoryLimit`/`failedJobsHistoryLimit`) are still set
  correctly post-suspend, per the task spec's instruction not to wait
  multiple minutes for pruning.
- Total live validator runtime for the full pass path (stock-fail check
  not included): ~70s, comfortably inside the ~5 min budget -- most of it
  is the 75s-budgeted wait for the CronJob's first spawn+completion,
  which resolved well before hitting its timeout.
- Live verification performed against the running `kind-sandbox20`
  cluster (images `sandbox20-app:1.0/2.0/distroless` already loaded,
  namespace `t02` from another in-progress task present and untouched):
  1. Stock stubs: `NOT PASSED: kubectl apply -f job.yaml failed: error:
     no objects passed to apply`, exit 1, zero traceback lines.
  2. Throwaway correct solution written directly into
     `src/job.yaml`/`src/cronjob.yaml` (sha256 snapshot of the stub
     content taken first), validator run to completion:
     `PASSED: Job 'rescrape' reached succeeded=4 with overlapping shard
     pods rescrape-brpd4/rescrape-hvsv9 (overlap window
     2026-07-23T11:43:03 -> 2026-07-23T11:43:07), resources/QoS correct;
     CronJob 'scheduled-scrape' structurally correct, spawned+completed
     Job 'scheduled-scrape-29746784', now suspended` -- exit 0, ~70s
     wall-clock.
  3. Reverted `src/job.yaml` and `src/cronjob.yaml` to the original stub
     content and verified byte-identical via `sha256sum` diff against the
     pre-throwaway snapshot -- identical.
  4. Re-ran the stock validator post-revert: identical `NOT PASSED` line
     as step 1, confirming the revert left no residue.
  5. Namespace `t03` confirmed `NotFound` after a short wait on both the
     failing-stub run and the passing-throwaway run; no other namespace
     touched.
- No reference solution committed anywhere -- the throwaway pass-path
  YAML only ever existed transiently in `src/*.yaml` during verification
  (and as prose/field values, not full YAML bodies, in this notes file),
  then was overwritten back to the stub content.
