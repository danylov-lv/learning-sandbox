# 10 — CrashLoopBackOff and distroless debugging

## Backstory

A config migration went out and took two services down with it. `ingest`
is stuck restarting -- every attempt to start ends the same way, fast. It's
never Ready long enough to matter. `render` looks calmer on the surface:
the container is `Running`, it never crashes, but it also never goes
`Ready`, and the Service in front of it has nothing healthy to send
traffic to. Same migration, two completely different failure modes, and
you get to sort out both.

## What's given

- `given/broken.yaml` -- three things, applied fresh into namespace `t10`
  by `given/setup.sh` (and independently by `tests/validate.py` itself, so
  the validator never depends on you having run `setup.sh` first):
  - a `ConfigMap` (`ingest-config`) and a `Deployment` (`ingest`,
    image `sandbox20-app:1.0`) that crash-loops.
  - a `Deployment` (`render`, image `sandbox20-app:distroless`) and a
    `Service` (`render`) where the pod comes up but never passes its
    readiness probe.
  - a standalone `Pod` (`render-debug-target`) -- same broken image and
    config as `render`, but **not** part of the Deployment, so nothing ever
    replaces it. This is your target for the ephemeral-container exercise
    below; don't delete it, and don't expect it to disappear when you fix
    the real `render` Deployment.
- `given/setup.sh` -- resets namespace `t10` and applies the fixture. Handy
  for poking around by hand; the validator doesn't need it.

**Do not edit `given/broken.yaml`.** Your fixes live in
`src/ingest-fix.yaml` and `src/render-fix.yaml` -- `kubectl apply` with
those re-patches the objects the fixture defines.

## What's required

**1. `ingest` (CrashLoopBackOff)** -- diagnose it with `kubectl logs
--previous`, `kubectl describe pod`, and `kubectl get events` before you
touch anything. The image checks a `REQUIRED_ENV` list of env var names at
startup and exits 1 (logging exactly which name is missing) if any of them
aren't set. Fix `src/ingest-fix.yaml` so the missing value is actually
supplied -- from the existing ConfigMap or a literal, your call -- so the
pod reaches `Ready`. Weakening `REQUIRED_ENV` instead of supplying the
value doesn't count; the validator checks that string is unchanged.

**2. `render` (stuck NotReady, no shell in the image)** -- the container
runs `gcr.io/distroless/python3-debian12`, which has no shell, no `sh`, no
`curl`. `kubectl exec -it <pod> -- sh` will fail outright. You need an
**ephemeral debug container** to investigate:

```bash
kubectl -n t10 debug -it render-debug-target \
  --image=sandbox20-app:1.0 --image-pull-policy=IfNotPresent \
  --target=render -- sh
```

Debug against `render-debug-target`, not the `render` Deployment's own
pod -- the Deployment's pod gets replaced the moment your fix rolls out, so
any evidence of ephemeral-container usage on it would vanish; the
standalone Pod stays around for the whole task. An ephemeral container
shares its target's network and process namespace, so from inside it you
can hit `localhost:<port>` directly or read `/proc/1/environ` to see what
the app was actually told to bind. Once you know the real port, fix
`src/render-fix.yaml` so `containerPort`/`readinessProbe` line up with
reality (or set the app's port back to what they already expect -- your
call which side moves).

**Anti-cheat, stated plainly:** `render` must keep running
`sandbox20-app:distroless`. Swapping it for `sandbox20-app:1.0` or `:2.0`
(both of which have a shell) to avoid the ephemeral-container exercise is
not a valid fix and the validator checks the image explicitly.

Both `src/*.yaml` files are currently `TODO(you)` skeleton comments with no
resource in them -- they fail cleanly (nothing to apply) rather than with a
YAML parse error. Read the comment block in each before writing: they call
out a real `kubectl apply` gotcha (three-way merge silently dropping fields
you don't re-list) that will bite you if you write a partial patch instead
of a complete object.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t10`, recreated on every run):

1. Applies `given/broken.yaml` and confirms the fixture is actually broken
   the way this README claims (ingest reaches `CrashLoopBackOff`, render
   stays at `readyReplicas: 0`, `render-debug-target` comes up `Running`)
   before giving any credit.
2. Applies your `src/ingest-fix.yaml` and `src/render-fix.yaml`.
3. Waits for both Deployments to roll out successfully, then checks:
   `ingest`'s `REQUIRED_ENV` is unchanged and `/env?name=CONFIG_QUEUE_URL`
   (through the running pod) echoes a real value; `render` still runs
   `sandbox20-app:distroless`, still has a `readinessProbe` on `/readyz`,
   and its Service actually serves `/` and `/readyz`.
4. Checks `render-debug-target` is still present, still `distroless`, and
   its `spec.ephemeralContainers` is non-empty -- proof you actually ran
   `kubectl debug` against it rather than reasoning your way to the answer
   from the YAML alone.

Namespace `t10` is deleted at the end whether you pass or fail.

## Estimated evenings

1

## Topics to read up on

- CrashLoopBackOff triage: `kubectl logs --previous`, `kubectl describe
  pod` (restart count, last exit code/reason), `kubectl get events
  --sort-by=.lastTimestamp`
- Readiness vs. liveness probes -- what a `Running`-but-never-`Ready` pod
  is telling you about which probe (if either) is actually failing
- Debugging shell-less/distroless images: `kubectl debug --target=` and
  ephemeral containers -- what namespaces they share with the target, and
  why `pod.spec.ephemeralContainers` persists on a pod even after the
  debug session ends
- Sourcing config from a `ConfigMap`/`Secret` via `env[].valueFrom` vs. a
  plain literal `value:`
- `kubectl apply`'s three-way strategic merge and why a partial patch can
  silently delete fields you didn't re-list

## Off-limits

`.authoring/design.md` and `.authoring/notes-t10.md` are spoiler-level
design material for this module -- don't read them before you're done with
this task.
