# 11 -- Arc 3 Capstone: The Incident

## Backstory

3am. The on-call phone doesn't ring for pods restarting -- it rings
because the public API is returning nothing. `curl` against it times out.
Whoever's on call pulls up `kubectl get pods -n t11` and sees exactly what
you'd expect from "the API is down": a Deployment that won't stay up.

That part's loud and easy. What makes this a real incident instead of a
one-line fix is what's sitting quietly *next to it*: a second component
that looks completely fine -- `Running`, no restarts, no errors in its
logs -- and yet, when someone finally thinks to check, has not actually
processed a single item in however long this has been going on. Nothing
about it ever paged anyone, because from its own point of view, nothing
is wrong. It's doing exactly what it was told to do.

Two symptoms. Two different components. Two different failure
signatures -- one loud, one silent. By the end of this task you'll know
they trace back to exactly one misconfiguration, and you'll have
restored the system without ever being told what that misconfiguration
was.

## What's given

```bash
bash given/setup.sh
```

resets namespace `t11` from scratch and applies a small pipeline:

- **`redis`** -- the queue backend. Healthy, not part of the incident.
- **`pipeline-config`** -- a ConfigMap read by all three app components
  below via `envFrom` (a whole-ConfigMap import, not a per-key reference).
- **`api`** -- the public-facing component (`WORK_MODE=server`, the
  fixture app's default), behind Service `api`, with `/readyz`.
- **`worker`** -- a consumer (`WORK_MODE=consumer`) draining the queue.
- **`producer`** -- pushes synthetic jobs onto the queue
  (`WORK_MODE=producer`).

All four workload manifests are given, unmodified, real Deployments --
this task is not "write a Deployment from a stub," it's "diagnose and fix
a live incident," the same way you would against a system you didn't
write. Don't read `given/*.yaml` before you've looked at the live cluster
first -- `given/setup.sh`'s own output tells you where to start looking.

**A note on the redis image**: `given/redis.yaml` uses `redis:t11-repack`,
already `kind load`-ed into the `sandbox20` cluster. It's a locally
rebuilt, single-platform repack of `redis:7-alpine` -- plain
`redis:7-alpine` carries multi-platform manifest-list metadata (including
a build-provenance attestation entry) that `kind load` cannot fully import
into containerd on this setup. The repack is bit-for-bit the same redis
binary and config layer; nothing about its behavior differs from stock
`redis:7-alpine`. This is infrastructure, not part of the incident -- you
don't need to do anything about it.

## What's required

1. **Diagnose from the live cluster**, the way you would a real incident:
   `kubectl -n t11 get pods`, `get events --sort-by=.lastTimestamp`,
   `logs <pod> --previous` for whatever's crashing, and something more
   than pod status for the component that isn't crashing but also isn't
   doing its job (there's a redis pod in this namespace -- ask it
   directly what it thinks the queue looks like).
2. **Find the one shared root cause.** Both visible symptoms trace back
   to exactly one wrong thing in exactly one place. Don't patch each
   symptom separately -- if your fix only makes one of the two go away,
   you fixed a symptom, not the cause.
3. **Fix it** by writing a corrected ConfigMap into
   `src/pipeline-config-fix.yaml` (a TODO stub right now). It gets
   applied on top of the seeded `given/pipeline-config.yaml` with
   `kubectl apply -f` -- a same-named object replaces the broken one
   wholesale.
4. **Write up the incident** in `INCIDENT.md`: symptoms, root cause,
   the cascade chain connecting one cause to two effects, how you
   actually localized it, and what would prevent this class of bug next
   time.

The validator doesn't care exactly which fields you touch to get there --
it seeds the broken state, applies whatever you put in
`src/pipeline-config-fix.yaml`, and checks the cluster ends up healthy.
How you got the ConfigMap right is up to you.

## Checkpoints

### CP1 -- health restoration (`tests/validate_cp1.py`)

The hard, fix-path-agnostic gate. The validator:

1. Seeds the incident fresh into `t11` (same as `given/setup.sh`).
2. Confirms it's actually broken the way this README claims -- `api` and
   `worker` both show `CrashLoopBackOff`, and the redis queue key is
   visibly growing with nobody consuming it. If this step fails, the
   fixture is broken, not your fix (this should never happen to you; it's
   here so a failure here is unambiguous).
3. Applies `src/pipeline-config-fix.yaml`, then rollout-restarts `api`,
   `worker`, and `producer` so each picks up the corrected config at a
   fresh container start. (A plain ConfigMap edit does not change an
   already-running container's resolved environment -- this restart is a
   normal ops step after any ConfigMap fix, not a hint about your
   specific answer.)
4. Asserts the healthy target state: every Deployment in `t11` available
   at full desired replicas, no pod anywhere in `t11` in
   `CrashLoopBackOff`, `/readyz` returns 200 through Service `api`, and
   the pipeline is actually flowing end to end (`worker`'s own
   `app_processed_total` rises over a real window -- not just "the pod is
   Running").
5. A durability check: scales `api` and `worker` to 0 replicas and back
   up, and re-asserts the same healthy target state against the fresh
   pods that come up -- proving your fix lives in the ConfigMap/Deployment
   objects themselves, not in one pod instance that happened to start
   after you patched something live.

Namespace `t11` is deleted at the end whether this passes or fails.

### CP2 -- incident writeup (`tests/validate_cp2.py`)

Fill in every section of `INCIDENT.md`, grounded in what you actually
observed (real object/field names, real command output) rather than
generic incident-response prose. The validator checks the sections are
filled in and reference this incident's actual vocabulary, then re-runs
`validate_cp1.py` as a real subprocess and requires it to still pass. A
writeup for a fix that no longer restores the cluster does not pass this
checkpoint either.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
```

Each prints exactly one `PASSED` (with a trailing detail) on success, or
one `NOT PASSED: <reason>` and exits 1 on failure -- no raw tracebacks.
Both need the `sandbox20` kind cluster up (`bash ../scripts/cluster-up.sh`
from the module root if it isn't) and the fixture images loaded (`bash
../scripts/build-images.sh`).

## Estimated evenings

1-2

## Topics to read up on

- Systematic incident triage in Kubernetes: what to check first
  (`get pods`), second (`get events --sort-by`), third (`logs --previous`
  for anything that's restarted) -- and why `--previous` matters
  specifically for a container that's already crash-looping.
- `envFrom: configMapRef` (whole-ConfigMap import) vs.
  `env: valueFrom: configMapKeyRef: key: ...` (single named key) -- why a
  typo'd key behaves completely differently under each: one fails loud at
  `kubectl apply`/pod-creation time, the other fails silently until
  something downstream notices a variable it expected is simply absent.
- Dependency-induced cascading failure: one shared misconfiguration
  reaching multiple consumers that each handle "this required thing is
  missing" differently -- fail fast and loud vs. silently fall back to a
  default.
- Readiness under dependency failure: why a component's own `/readyz` can
  stay green even while the thing it depends on is completely broken, if
  the readiness check was never wired to actually depend on it.
- Why a plain `kubectl apply` to a ConfigMap does not retroactively change
  an already-running container's resolved environment, and what forces a
  container to re-resolve it (a fresh container start -- crash-loop
  restart, `kubectl rollout restart`, or a full pod recreation).

## Off-limits

`.authoring/design.md` (at the module root) holds this module's full
infrastructure contract, including this task's verification approach in
more explicit detail -- spoilers. Don't read it before you're done with
this task.
