# Authoring notes -- 08-rightsizing-and-oomkill

Empirics from live verification on the real `sandbox20` cluster with a
throwaway reference `src/deployment.yaml` + filled `NOTES.md` (built in
place, never committed, reverted byte-identical afterward -- sha256
matched before/after for both files).

## Gotcha: containerd 2.0 / kind does not reliably report `reason: OOMKilled`

This is the single biggest surprise and it shapes the whole task design.
On this cluster (containerd `v2.0.3`, kubelet `v1.32.2`), a container
genuinely killed by the cgroup OOM killer consistently reports
`state.terminated.reason: "Error"`, not `"OOMKilled"`, even though:

- `exitCode` is reliably `137` (128 + SIGKILL) every time, and
- the node's kernel log (`docker exec <node> dmesg`) unambiguously shows
  `Memory cgroup out of memory: Killed process ... (python)` for the
  exact PID/cgroup involved.

I confirmed this across four independent test pods with different
`LEAK_MB_PER_S`/limit combinations (5/128Mi observed via the pre-existing
`t08-scratch/oom-victim` leftover, then 16/96Mi, 4/200Mi, and an immediate
`MEM_MB=500`/`limits.memory:100Mi` overshoot case I ran myself) -- every
single one: `exitCode: 137`, `reason: "Error"`. This is not a race/timing
issue (I tried a 50s-lifetime case specifically to give the kubelet's
housekeeping cycle time to catch it, no change). It looks like a genuine
regression/behavior change in how newer containerd reports OOM to the
kubelet that this k8s version doesn't recognize correctly.

**Design decision**: the validator asserts `exitCode == 137` and never
asserts on the `reason` string. The README, hint-3, and NOTES.md all call
this out explicitly as a real, worth-knowing platform quirk ("trust the
exit code, not the reason string") rather than hiding it -- it's honestly
a better lesson than a clean `OOMKilled` string would have been.

## Reused a previous session's leftover fixtures as calibration data

`t08-scratch` namespace already existed on the cluster (age ~6h at start
of this session) containing a `mystery-worker` Deployment
(`MEM_MB=180`, `CPU_BURN_THREADS=1`, 2 replicas, no resources) and an
`oom-victim` Pod (`LEAK_MB_PER_S=5`, `requests: cpu 50m/memory 64Mi`,
`limits: memory 128Mi`, already `Error`/exitCode 137 by the time I looked
at it). These are almost certainly leftovers from an earlier, apparently
interrupted authoring attempt at this exact task -- the parameters are
too specific to be coincidence. Per instructions I left `t08-scratch`
untouched (did not delete it, did not build on top of it), but I did reuse
its exact numbers as calibration since they were already empirically
verified to work on this cluster: `MEM_MB=180`/`CPU_BURN_THREADS=1` for
the profiling fixture, and `LEAK_MB_PER_S=5` + `limits.memory: 128Mi` for
the OOMKill fixture, landing on the same design independently.

## Calibration numbers observed (live, via `given/observe-rightsizing.sh`)

- `profile-me` (`MEM_MB=180`, `CPU_BURN_THREADS=1`, no resources set):
  `kubectl top pod --containers` reported ~202Mi memory, ~1092m CPU,
  consistent across two separate measurements ~6h apart (202Mi/203Mi,
  1091-1092m). Stable, not noisy -- good for a deterministic policy-cap
  design.
- Chosen policy caps: `limits.memory <= 320Mi` (~58% headroom over the
  202Mi measured baseline -- enough for real margin, not enough to allow
  "just set it to 1Gi to be safe"), `limits.cpu <= 1500m` (~37% headroom
  over the measured ~1092m).
- Reference solution used `requests: {cpu: 200m, memory: 160Mi}`,
  `limits: {cpu: 1200m, memory: 256Mi}` -- passed cleanly.

## OOMKill window observed (`given/leak-pod.yaml`, `LEAK_MB_PER_S=5`, `limits.memory: 128Mi`)

Consistently ~20-25s from pod start to `Failed` phase across multiple
runs (the pre-existing `oom-victim` fixture: 22s; my own fresh apply
during this session: ~20s). Validator uses a 120s bounded poll, which is
generous (5-6x the observed window) without being a fixed wall-clock
perf gate -- it's a correctness timeout ("did this terminate at all"),
not a speed grade.

## Stock-fail line (unfilled stubs)

```
NOT PASSED: kubectl apply -f deployment.yaml failed: error: no objects passed to apply
```

Exactly one line, exit 1, zero traceback lines. Confirmed by running
`uv run python tests/validate.py` against the stock stub twice (before
writing the reference solution, and again after reverting it).

## Reference pass-path confirmation

Filled `src/deployment.yaml` (rightsize-me, requests/limits above) +
filled `NOTES.md` (all four sections, throwaway reference content marked
`REFERENCE-ONLY (throwaway, will be reverted)` inline so it was never
ambiguous which text was permanent) → validator printed:

```
PASSED: 'rightsize-me' pod rightsize-me-<hash> healthy under load with resources within policy caps; 'leak-victim' OOMKilled as expected (exitCode 137); NOTES.md complete
```

Also spot-checked two failure paths with the reference deployment:
- `limits.memory: 512Mi` (over the 320Mi cap) → clean structural
  `NOT PASSED` naming the exact cap violated, no pods even applied yet.
- `limits.memory: 192Mi` (below the ~202Mi measured working set) → pod's
  container terminated with `exitCode=137, reason='Error'` during the
  Ready-wait, surfaced as a specific `NOT PASSED` naming OOMKill as the
  likely cause, not a generic timeout.

Both stub files reverted byte-identical afterward:
`src/deployment.yaml` sha256
`915894422b4d92d59b56b70e86bfe22abdccd4406ff9d28c431bca8365eeb040`,
`NOTES.md` sha256
`d51b90663e8a08762b667bb45575d0b8094a32a4292e1e0ba856bf1085f518ef`
-- both matched before and after.

## NOTES.md doc-gate design note

Deliberately kept the section prompts in `NOTES.md` terse (one line each)
and free of the grading keywords themselves (no "requests"/"limits"/
"QoS"/"OOMKilled"/"137"/"cgroup"/etc. in the unfilled template's section
bodies) specifically so that `check_sections`'s length/placeholder check
and `check_keywords`'s vocabulary check can't be cleared by simply
deleting the `[fill in]` line -- verified this holds by running
`check_sections`/`check_keywords` directly against the stock template
(would need real learner content to pass) and against the filled
reference (passes at `min_hits=9` of 14 keywords, `min_chars=300`/section).

## Cleanup performed

- `kubectl delete ns t08` at the end (namespace created by my own
  validator runs during verification).
- Left `t08-scratch` untouched (pre-existing, not created by this
  session).
- Left metrics-server installed (this task owns it; confirmed
  `kubectl top nodes`/`kubectl top pods` both work).
- No node taints/labels added (this task doesn't need any); confirmed
  no `s20-t08/*` labels/taints exist on any node.
