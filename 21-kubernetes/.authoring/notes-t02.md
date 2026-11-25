# Authoring notes -- 02-probes-and-zero-downtime

- **Why the broken fixture actually fails, mechanistically (worth
  understanding before touching the validator):** with no `readinessProbe`,
  a pod is added to the Service's Endpoints as soon as its container is
  `Running` -- kubelet's default readiness state, absent a probe, is
  `True`. Combined with `START_DELAY_S=8`, every fresh pod is a valid
  (but non-functional) endpoint for its first 8 seconds. Separately, the
  `livenessProbe` (`initialDelaySeconds: 2, periodSeconds: 2,
  failureThreshold: 1`) fires at ~t+2s and gets connection-refused (app
  hasn't bound the port yet) -- kubelet decides to kill the container. It
  sends `SIGTERM`, but `TERM_IGNORE=1` means the app ignores it, so kubelet
  has to wait the full `terminationGracePeriodSeconds` (default 30s, not
  overridden in the broken fixture) before `SIGKILL`. Crucially, the OLD
  container process is still running (and un-terminated) during that whole
  30s wait -- so the app's own 8s startup sleep completes *inside that same
  process* around t+8s, and the pod actually serves correctly from ~t+8s to
  ~t+30s, then gets hard-killed and the whole cycle repeats in the new
  container. Net effect: a restart roughly every ~30s per pod, and a
  dropped-request rate roughly proportional to the "actually dead" fraction
  of each ~30s cycle (from container start to ~8s). This is a more
  interesting failure signature than "perpetual sub-second crash loop" --
  worth calling out for anyone extending this fixture later.

- **Broken-fixture live measurement** (via `given/observe.sh`, 60s load
  window, `t02`, 3 replicas, rollout `1.0 -> 2.0` triggered mid-load):
  `RESULT ok=620 fail=287` (~31.6% failure rate over 907 requests),
  restart count 1 per pod within the ~85s wall-clock window the script
  runs for (consistent with the ~30s-per-cycle mechanism above -- a 60-90s
  window catches roughly one full cycle per pod). Confirmed non-vacuous
  and reproducible across multiple runs during authoring (a separate,
  longer standalone observation with no rollout at all, just the broken
  Deployment sitting there, showed restart counts climbing by 1 roughly
  every 15-30s indefinitely over several minutes -- same underlying cause,
  no rollout needed to see it).

- **Anti-cheat is intentionally permissive on the TERM_IGNORE question, the
  behavioral load test is the real bar.** The structural check accepts
  either "TERM_IGNORE absent" OR "preStop present" (matching the module
  design doc's "either acceptable" framing). But empirically, removing
  `TERM_IGNORE` *alone* (default graceful SIGTERM handling, no `preStop`,
  default `terminationGracePeriodSeconds`) is NOT reliably zero-drop under
  load: measured 5 failed requests out of 1195 (~0.4%) during one rollout
  trial -- `Connection refused` / `Connection reset by peer` /
  `timed out`, consistent with the well-known kube-proxy/iptables
  endpoint-removal-propagation race (the pod stops accepting connections
  at the moment its own SIGTERM handling runs, which can be a hair before
  every node's routing rules have caught up with its removal from
  Endpoints). Adding `lifecycle.preStop: {exec: {command: ["sleep", "5"]}}`
  plus `terminationGracePeriodSeconds: 40` (with `TERM_IGNORE` also
  removed) closed this gap completely: 3 separate full-rollout trials,
  1235-1238 requests each, 0 failures every time. The task doesn't require
  learners to add `preStop` structurally, but a learner who only removes
  `TERM_IGNORE` and skips `preStop` will most likely see occasional
  `NOT PASSED: load generator saw N failed request(s)` and need to add it
  to get a deterministic pass -- this is by design (the validator grades
  the outcome, not the mechanism) and is called out in hint-2/hint-3 as
  "don't take it on faith, measure."

- **Load generator design:** an in-cluster `Pod` running
  `sandbox20-app:1.0` (already `kind load`ed, no registry/pull needed) with
  `command: ["python3", "-c", <script>]` -- the script is a stdlib-only
  (`urllib.request`) loop against `http://web.t02.svc.cluster.local/work?
  ms=20`, printing a final `RESULT ok=<n> fail=<n>` line plus up to 8
  `EXAMPLE <error>` lines on completion. Chosen over a `busybox`/`wget`
  pod (confirmed pullable -- cluster nodes do have internet egress in this
  environment -- but there's no reason to depend on that when the fixture
  app image already has everything needed and is guaranteed loaded).
  Explicitly NOT a port-forward: port-forward pins traffic to one pod's
  local proxy and never exercises the Service's actual load-balancing /
  endpoint-removal behavior, which is exactly what this task is testing.

- **Calibration for `tests/validate.py`:** `LOAD_DURATION_S=150`,
  request interval 0.05s (~13-16 req/s observed in practice, timeout=2s
  per request). A full rollout (3 replicas, `maxSurge>=1`/
  `maxUnavailable=0`, 8s startup each) measured at roughly 40-70s wall
  clock across trials; 150s of sustained load gives wide margin on both
  sides (baseline traffic before the rollout starts, tail traffic after it
  finishes). `wait_rollout` timeouts set to 180s (both initial apply and
  the `1.0 -> 2.0` update) for the same reason -- generous, not tuned to
  one run. Across every throwaway-solution trial run during authoring,
  request counts landed in the 1200-2100 range depending on exact timing
  and 0 failures every time -- deterministic in practice.

- **`containerStatuses[].image` is not what you'd guess.** The container
  spec field is `sandbox20-app:2.0` (matches `imagePullPolicy: Never`,
  no registry), but the live pod's `status.containerStatuses[].image` is
  reported as `docker.io/library/sandbox20-app:2.0` (containerd's fully
  qualified form). First validator draft compared for exact equality and
  false-failed a genuinely-passing solution; fixed to check
  `image.endswith("sandbox20-app:2.0")`.

- Live verification performed against the running `kind-sandbox20` cluster
  (images `sandbox20-app:1.0/2.0/distroless` already loaded), namespace
  `t02` only:
  1. `given/broken-deployment.yaml` + `given/service.yaml` applied
     standalone (outside `observe.sh`) and watched directly for several
     minutes: confirmed real, ongoing restarts (not a one-off) -- see
     mechanism note above.
  2. `given/observe.sh` run end-to-end: measured numbers above
     (`ok=620 fail=287`, 1 restart/pod). Script correctly does not hard-fail
     when `kubectl rollout status` happens to time out (broken probes can
     make convergence non-deterministic); it still collects and prints the
     load-generator result and restart counts either way.
  3. Stock `src/deployment.yaml` stub (comment-only TODO block) ->
     `NOT PASSED: kubectl apply -f .../src/deployment.yaml failed: error:
     no objects passed to apply`, exit 1, single line, no traceback.
  4. Throwaway correct solution (probes + `preStop`/`terminationGrace
     PeriodSeconds` + `maxSurge:1`/`maxUnavailable:0`, `TERM_IGNORE`
     removed) written directly into `src/deployment.yaml`, validator run
     to `PASSED: zero-downtime rollout to 2.0 confirmed: 2068 requests,
     0 failures, 0 container restarts`, exit 0.
  5. `src/deployment.yaml` reverted to the original stub content and
     verified byte-identical via `sha256sum` against a hash snapshot taken
     before the throwaway write (`e3cbf9444db6e5e72d2329390e04e5b8c151fd7
     ef22b1655138283853980ee44`, matched exactly).
  6. Re-ran the stock validator post-revert: identical `NOT PASSED` line as
     step 3, confirming the revert left no residue.
  7. Namespace `t02` confirmed deleted (`NotFound`) after each run
     (stock-fail path and pass path both trigger the `finally: delete_ns`);
     no other namespace touched.

- No reference solution committed anywhere -- the throwaway pass-path YAML
  only ever existed transiently in `src/deployment.yaml` during
  verification (and in this notes file's prose description above, no YAML
  bodies pasted here), then was overwritten back to the stub content.
