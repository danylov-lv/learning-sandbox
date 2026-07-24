# 08 — Right-sizing and OOMKill

## Backstory

Someone on your team deployed a worker with no `resources` block at all
("it worked in dev") and now it's either starving next to a noisy neighbor
or getting silently murdered by the kernel the moment traffic picks up.
Both of those are things Kubernetes does *on purpose*, based entirely on
the numbers you write into `resources.requests` and `resources.limits` --
there's no magic autodetection, and guessing round numbers instead of
measuring is how you end up back here at 2am.

This task has two halves that use the same fixture app in two different
failure modes:

- **Right-sizing**: a workload with a real, non-trivial memory/CPU
  footprint that you have to *measure* (`kubectl top`, via metrics-server)
  before you can pick sane `requests`/`limits` for it. Guess too low and
  it gets OOMKilled under this task's own grading run; guess absurdly high
  "to be safe" and it fails a stated policy cap instead -- there is an
  actual right answer here, not just "bigger is safer."
- **OOMKill**: a container with `LEAK_MB_PER_S` set -- it grows its own
  resident memory forever, by design, with nothing in the app itself to
  stop it. The only thing that can ever stop it is the pod's own memory
  limit, and it *will* get killed for going over it. Recognizing that
  event correctly (exit code, not vibes) is the point.

## What's given

- `given/install-metrics-server.sh` (+ `uninstall-metrics-server.sh`) --
  installs metrics-server cluster-wide, patched for kind's self-signed
  kubelet certs (`--kubelet-insecure-tls`). This is a cluster-global
  install owned by this task (see `.authoring/design.md`): every later
  task assumes it is already installed. **Run it before anything else in
  this task**:

  ```bash
  bash given/install-metrics-server.sh
  ```

  It's idempotent and waits until `kubectl --context kind-sandbox20 top
  nodes` actually returns numbers before exiting. Do not run
  `uninstall-metrics-server.sh` -- other tasks in this module depend on it
  staying installed.

- `given/profile-workload.yaml` -- a ready-to-apply Deployment
  (`profile-me`) with `MEM_MB=180`, `CPU_BURN_THREADS=1`, and **no**
  `resources` block at all, so it schedules as `BestEffort` and you can
  watch its real footprint with `kubectl top` before writing anything.
  This is not what gets graded -- it exists purely so you have something
  to measure. `given/observe-rightsizing.sh` applies it and prints
  `kubectl top pod --containers` for you.

- `given/leak-pod.yaml` -- a ready-to-apply Pod (`leak-victim`) with
  `LEAK_MB_PER_S=5`, `requests: {cpu: 50m, memory: 64Mi}`,
  `limits: {memory: 128Mi}`. This is the scripted OOMKill demonstration;
  you don't edit it, the validator applies it exactly as given.
  `given/observe-oomkill.sh` applies it, waits for it to die, and prints
  the container's exit code and termination fields.

## What's required

### Part 1 -- `src/deployment.yaml` (right-sizing, graded)

Currently a `# TODO(you): ...` skeleton comment block -- `kubectl apply -f
src/deployment.yaml` applies nothing until you write the real object.

Write a Deployment:

- `metadata.name: rightsize-me`, `spec.replicas: 1`.
- pod template labels (and `selector.matchLabels`) `app: rightsize-me`.
- container `image: sandbox20-app:1.0`, `imagePullPolicy: IfNotPresent`,
  `containerPort: 8080`.
- env vars **exactly** `MEM_MB: "180"` and `CPU_BURN_THREADS: "1"` --
  same knobs as `given/profile-workload.yaml`, so what you measured there
  transfers directly.
- `resources.requests` **and** `resources.limits`, both with `cpu` and
  `memory` set, based on what `kubectl top` actually showed you. Two hard
  policy caps apply regardless of what you measured (this is deliberate --
  see "Topics to read up on"):
  - `limits.memory` must be **at most `320Mi`**.
  - `limits.cpu` must be **at most `1500m`**.

  Set the limit too low relative to what this workload actually needs and
  it will get OOMKilled during the validator's own load run, the same way
  `leak-victim` does in Part 2 -- that failure mode is not hypothetical,
  it's exactly what this task is built to let you trigger on yourself.

### Part 2 -- OOMKill fixture (given, no manifest to write)

Nothing to author here -- `given/leak-pod.yaml` is fixed. Your job is to
run it (`given/observe-oomkill.sh`, or apply it by hand), read what
actually happens to it, and write about it correctly in `NOTES.md`
(see below). The validator applies this exact fixture itself and checks
the outcome independently of anything you do.

One honest platform note, since it'll look like a bug the first time you
see it: on this cluster's containerd/kubelet combination, the killed
container's `state.terminated.reason` field frequently reads `Error`
rather than the friendlier `OOMKilled` string, even though it was
genuinely OOM-killed (confirmed via the node's kernel log, which reports
`Memory cgroup out of memory: Killed process ...`). **`exitCode: 137`
(128 + `SIGKILL`'s signal number 9) is the reliable, portable signal** --
the `reason` string is not. This task's validator checks the exit code,
not the reason string, for exactly that reason.

### `NOTES.md` -- graded write-up

Fill in every section (replace every `[fill in]`). This file is graded:
the validator checks that every required section is present, non-empty,
free of leftover `[fill in]` markers, and grounded with real vocabulary
from this task (not just restated prose). See the file itself for the
exact sections and what each one is asking for.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t08`, recreated fresh, deleted at the end
whether you pass or fail):

1. Confirms metrics-server is installed and `kubectl top nodes` works
   (run `given/install-metrics-server.sh` first if this fails).
2. Applies `src/deployment.yaml` and checks the structural contract: env
   vars, both `requests` and `limits` present with `cpu` and `memory` on
   each, and the two policy caps (`limits.memory <= 320Mi`,
   `limits.cpu <= 1500m`).
3. Waits (bounded) for the `rightsize-me` pod to become Ready. If it gets
   OOMKilled or restarts instead, you get a specific failure message
   naming that, not a generic timeout.
4. Port-forwards straight to the pod and drives a short burst of
   `/work?ms=N` requests through it, asserting every response is 2xx and
   the pod is still Running/Ready with zero restarts afterward
   (behavioral -- no wall-clock performance gate, just "did it survive
   real traffic without falling over").
5. Applies `given/leak-pod.yaml` (its own copy, independent of anything
   you ran manually) and waits (bounded, generous) for the container to
   terminate, asserting `exitCode == 137`.
6. Runs the `NOTES.md` doc-gate: required sections present, filled in,
   and grounded with the vocabulary this task is actually about.

## Estimated evenings

1

## Topics to read up on

- `resources.requests` vs `resources.limits` -- what each one actually
  controls (scheduling decision vs. hard enforced ceiling), and why "just
  set limits very high" is not free: it's exactly the failure mode Part 1's
  policy caps are designed to catch (over-provisioning starves the rest of
  the node of schedulable capacity even when nothing is actually using it).
- Kubernetes QoS classes (`Guaranteed`, `Burstable`, `BestEffort`) and how
  they're derived purely from the requests/limits numbers you write, plus
  why QoS class drives eviction order under node memory pressure.
- OOMKill mechanics: cgroup memory limits, `exitCode 137` (`128 + SIGKILL`),
  and why the human-readable `reason` field reported by the container
  runtime is not always trustworthy evidence even when the numeric exit
  code is.
- The difference between "resident memory" (what a process is actually
  holding, what `kubectl top` shows you) and the raw knob values you set
  on a fixture -- real processes always cost more than their nominal
  payload.
- Right-sizing methodology in general: measure first, decide margin
  second, and treat "how much headroom is enough" as a real question with
  a real answer, not an excuse to over-provision indefinitely.
