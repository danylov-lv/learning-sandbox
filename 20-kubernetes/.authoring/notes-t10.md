# Task 10 authoring notes (crashloop-and-distroless)

## Ephemeral-container evidence contract chosen: (a), dedicated long-lived pod

Went with design.md's recommended option (a): `given/broken.yaml` now
defines a third object beyond the two Deployments -- a standalone Pod
`render-debug-target`, same image (`sandbox20-app:distroless`) and same
broken env (`PORT=9090`) as the `render` Deployment's pod, but not owned by
any ReplicaSet and never touched by the learner's fix. It has no
readinessProbe (a bare Pod's containerStatus is considered `ready` once
`Running` with no probe configured), so it sits `1/1 Running` forever --
always there to attach an ephemeral container to, before and after the
learner fixes the real Deployment.

Rejected the naive "check `pod.spec.ephemeralContainers` on whichever pod
currently backs the `render` Deployment" because the fix triggers a new
rollout -> new pod -> new pod has an empty `ephemeralContainers` list -- the
evidence would be destroyed by the very act of passing the other half of
the task. Confirmed this live before the design decision (see empirics
below): `ephemeralContainers` persists on a pod object indefinitely (even
after the ephemeral container's process exits, `state.terminated` just
sits there), but it does NOT propagate to a replacement pod -- it's
per-pod-object, not per-Deployment. Option (a) sidesteps this entirely by
having the debug target be a pod that structurally cannot be replaced by
the learner's fix (it isn't in the Deployment's template).

Did not need option (b) (doc-gate via DIAGNOSIS.md/NOTES.md) as a
supplement -- (a) alone is fully verifiable and non-gameable:

- `render-debug-target`'s own container image is checked (must stay
  `sandbox20-app:distroless`) so a learner can't dodge the anti-cheat by
  deleting this pod and recreating a shell-having lookalike under the same
  name.
- Deliberately gave `render-debug-target` a DIFFERENT label
  (`app: render-debug-target`) from the real `render` pods (`app: render`)
  so it never becomes an accidental endpoint of the `render` Service
  (Service selector is `app: render`; if the debug pod matched, it'd get
  load-balanced traffic on port 8080 while actually listening on 9090,
  polluting the render-Service behavioral check with an unrelated pod).
- `NOTES.md` has an unfilled, non-graded "which port / which command"
  section for the learner's own benefit, but it's explicitly NOT part of
  the pass/fail gate -- kept it that way since (a) alone is sufficient and
  I didn't want a doc-gate silently allowing a learner to fabricate the
  ephemeral-container claim in prose while never actually running the
  command. Structural (a) is strictly stronger for this specific claim.

## Discovered-port empirics (live, against kind-sandbox20 / t10)

- `render`'s container declares `containerPort: 8080` + readinessProbe on
  `8080`, but `env: PORT=9090` means the app binds `9090`. Verified via
  ephemeral container attached to `render-debug-target`:
  `curl`/`wget` are NOT present in `sandbox20-app:1.0` (python:3.11-slim
  based) -- use `python3 -c "import urllib.request; ..."` instead, or read
  `/proc/1/environ` (ephemeral container shares the target's PID namespace
  since `--target=render` was passed). Confirmed:
  `GET http://localhost:9090/readyz` -> `ready`, and
  `GET http://localhost:8080/readyz` -> `Connection refused`.
- `pod.spec.ephemeralContainers` is populated and PERSISTS on the pod
  object immediately after the debug session, including after the
  ephemeral container itself terminates (`status.ephemeralContainerStatuses[].state.terminated`,
  `exitCode: 0`). This is what the validator's final check reads.
- Confirmed the render Service does NOT need editing under either fix
  strategy, because `targetPort: http` is name-based, not a raw port
  number -- it always resolves to whatever `containerPort` entry is named
  `http`, regardless of the numeric value. Chose the reference fix
  (throwaway, never committed) of moving `containerPort`/`readinessProbe`
  to `9090` rather than reverting `PORT` to `8080` -- either is
  structurally acceptable per the stub comments and the validator doesn't
  care which side moved, it only drives traffic through the Service and
  checks for 200s.

## Stock-fail line (unfilled `src/*.yaml` stubs)

```
NOT PASSED: D:\Programming\Sandbox\learning-sandbox\20-kubernetes\10-crashloop-and-distroless\src\ingest-fix.yaml still looks like the unfilled TODO stub
```

Exit code 1, single line, no traceback. Confirmed twice (once before
writing the throwaway reference fix, once again after reverting to stock
and cleaning the cluster) -- both runs identical.

## Reference-pass confirmation

Wrote throwaway `src/ingest-fix.yaml` (ConfigMap gets a new `QUEUE_URL`
key, Deployment adds `CONFIG_QUEUE_URL` via `configMapKeyRef`, full object
re-specified per the three-way-merge gotcha) and `src/render-fix.yaml`
(full Deployment, `containerPort`/`readinessProbe` moved to `9090`, image
kept `distroless`). Ran `tests/validate.py` in the background; while it
was mid-run (after it seeds the fixture, before its own final check), ran
the real `kubectl debug -it render-debug-target --image=sandbox20-app:1.0
--target=render -- sh -c "echo debug-session-ok"` by hand from a separate
shell to simulate the learner's actual workflow (the validator's own
seeding doesn't itself create the ephemeral container -- that's the whole
point, it has to be the learner/operator doing it). Result:

```
PASSED: ingest fixed (CONFIG_QUEUE_URL supplied, REQUIRED_ENV intact), render fixed and still distroless, ephemeral debug container evidence found on render-debug-target
```

sha256 of both `src/*.yaml` stubs + `NOTES.md` recorded before writing the
throwaway fix, reverted byte-for-byte after, re-hashed -- identical
(`diff` of before/after hash files: empty). No reference solution was
committed; the throwaway files only ever existed on disk during this
verification pass and were overwritten back to the TODO stub immediately
after.

## Caveats / things a future editor of this task should know

- `render-debug-target` has no liveness/readiness probe by design -- if
  someone "fixes" the fixture by adding one, `kubectl debug` still works
  the same way, but the pod's Ready condition would then depend on which
  port the probe targets, which isn't the point of this pod and would just
  add noise.
- The non-vacuous check waits for `ingest` to accumulate >= 2 restarts or
  see `waiting.reason == CrashLoopBackOff`, up to 120s. On a loaded
  machine the backoff schedule (10s, 20s, 40s...) means this can take
  ~30-60s in practice before the second restart lands; 120s leaves
  generous margin without being a tuned wall-clock gate.
- Namespace `t10` is fully deleted at the end of every validator run
  (pass or fail), so nothing from this task lingers on the shared cluster.
