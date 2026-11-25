# 02 — Probes and zero-downtime rollouts

## Backstory

Someone on your team wrote a Deployment for the fixture app. It works: `kubectl
apply` it and three pods come up, the Service resolves, `curl` returns 200.
Looks done. Then someone ships a new image tag, runs the totally ordinary
`kubectl set image ...`, and the on-call channel lights up: dropped requests,
pods restarting in a loop, users staring at 502s during what should have been
a boring rolling update.

Nothing about the app changed between "works" and "outage." What changed is
that a rollout is the first time Kubernetes actually exercises the contract
your probes make with reality — and this Deployment's probes are lying. It has
no `readinessProbe`, so the Service treats a pod as a valid destination the
instant its container is `Running`, whether or not the app inside has actually
bound its port yet. It has a `livenessProbe` tuned for an app that starts
instantly, pointed at an app that deliberately doesn't (`START_DELAY_S=8`).
And when Kubernetes tries to terminate a pod gracefully, the app ignores it
(`TERM_IGNORE=1`) and has to be killed the hard way after a long, silent wait.

## What's given

- `given/broken-deployment.yaml` — Deployment `web`, 3 replicas, image
  `sandbox20-app:1.0`, `START_DELAY_S=8` and `TERM_IGNORE=1` set, no
  `readinessProbe`, an aggressive `livenessProbe` on `/healthz`, and a rolling
  update strategy (`maxSurge: 0` / `maxUnavailable: 50%`) that throws away
  capacity during any update. This is broken on purpose — do not start your
  fix from a blank page, start by understanding exactly why each of these
  choices hurts.
- `given/service.yaml` — a plain ClusterIP Service in front of it.
- `given/observe.sh` — applies the broken fixture into namespace `t02`, starts
  an in-cluster load generator against the Service, triggers `kubectl set
  image` to `sandbox20-app:2.0` partway through, and prints what actually
  happened: request success/failure counts and container restart counts.

**Run `given/observe.sh` before writing anything.** Read its output. You
should see a meaningful chunk of failed requests and at least one container
restart — if you don't, something about your cluster/environment differs from
what this task expects and you should sort that out before continuing (see
`.authoring/notes-t02.md`-style empirics aren't shown to you here, but the
validator recreates the exact same conditions, so a clean `observe.sh` run is
real signal).

## What's required

Fix `src/deployment.yaml` (a TODO skeleton right now) into a Deployment that
survives the same `1.0 -> 2.0` rollout with **zero dropped requests and zero
container restarts**, while keeping the slow-start fixture in place. Concretely:

1. Keep `env: START_DELAY_S: "8"`. Deleting it or setting it to `0` doesn't
   fix your probes, it just removes the thing they were supposed to survive —
   the validator checks this env var is still exactly `"8"`.
2. Add a `startupProbe` that actually gives the app room to bind its port
   before liveness/readiness get a vote. Think about what "covers an 8 second
   startup" means in terms of `periodSeconds` × `failureThreshold`.
3. Add a `readinessProbe` on `/readyz` so the Service only ever routes to a
   pod whose app has actually said "I'm ready" — not one that merely exists.
4. Retune `livenessProbe` so it can only ever fire on a pod that's genuinely
   stuck, not one still inside a normal startup window.
5. Deal with `TERM_IGNORE`. You have two acceptable paths:
   - Remove it, so the app's default SIGTERM handling (drain in-flight
     requests, then exit) applies; or
   - Keep it and add a `lifecycle.preStop` hook (with
     `terminationGracePeriodSeconds` long enough to cover it) that gives the
     Service time to stop sending the pod new traffic before the container
     stops accepting connections.

   Either path can pass. What's graded is the outcome, not which one you pick
   — and you should verify for yourself which one (or which combination)
   actually gets you to zero dropped requests under real load. Don't assume;
   measure, the same way `observe.sh` measures the broken version.
6. Change the rolling update strategy so it never drops below full capacity:
   `maxUnavailable: 0`, `maxSurge` at least `1`.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator (namespace `t02`, recreated on every run):

1. Applies `given/service.yaml` and your `src/deployment.yaml` (expected to
   start at image `sandbox20-app:1.0`) and waits for the initial rollout.
2. Checks a handful of structural facts on the live Deployment: `START_DELAY_S`
   is still `"8"`, a `readinessProbe` targets `/readyz`, a `startupProbe`
   exists, `TERM_IGNORE` is gone or a `preStop` hook is present, and the
   rolling update strategy keeps full capacity.
3. Starts an in-cluster load generator that hammers the Service continuously
   (not a port-forward — that pins one pod and defeats the point of testing
   the Service's routing behavior).
4. Runs `kubectl set image deployment/web web=sandbox20-app:2.0` while that
   load is running, and waits for the rollout to finish.
5. Asserts the load generator logged **zero** failed requests and a healthy
   number of successful ones, every pod ended up on `2.0`, and total container
   restarts across all `web` pods is **zero**.

Namespace `t02` is deleted at the end whether you pass or fail.

## Estimated evenings

1

## Topics to read up on

- `readinessProbe` vs `livenessProbe` vs `startupProbe` — what each one
  actually gates (Service endpoints vs. container restarts vs. suppressing
  the other two probes during a slow boot)
- `initialDelaySeconds` / `periodSeconds` / `failureThreshold` / `timeoutSeconds`
  and how they combine into "how long before this probe can fail once, and
  how long before repeated failures actually do something"
- `RollingUpdate` strategy fields `maxSurge` / `maxUnavailable` and what each
  one trades off (capacity vs. resource headroom) during a rollout
- Pod termination lifecycle: SIGTERM, `terminationGracePeriodSeconds`,
  `lifecycle.preStop`, and why "the Service stops routing to a pod" and "the
  pod stops accepting connections" are two different events that can race
- why a Service can still send traffic to a pod that's `Running` but not
  actually accepting connections yet, absent a `readinessProbe`

## Off-limits

`.authoring/design.md` and `.authoring/notes-t02.md` are spoiler-level design
material for this module — don't read them before you're done with this task.
