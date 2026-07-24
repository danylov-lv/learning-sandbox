# Authoring notes -- task 11 (arc3-capstone-incident)

## Incident design

Namespace `t11`, five objects seeded by `given/`: `redis` (Deployment +
Service, healthy), `pipeline-config` (ConfigMap, the root cause lives
here), `api` (Deployment + Service, `WORK_MODE=server`), `worker`
(Deployment + Service, `WORK_MODE=consumer`), `producer` (Deployment,
`WORK_MODE=producer`).

**Root cause (ONE)**: `pipeline-config`'s `data:` has the intended key
`QUEUE_KEY` mistyped as `QUEUE_KEE`. All three app Deployments import the
whole ConfigMap via `envFrom: configMapRef` (not per-key
`configMapKeyRef`, deliberately -- a per-key ref would produce a loud
`CreateContainerConfigError` at pod-creation time for a missing key,
which defeats the "silent" half of the cascade). `envFrom` simply never
produces an env var named `QUEUE_KEY` for any of the three containers,
since no such key exists in the map.

**Cascade (2 distinct symptom classes from the one typo)**:
- `api` and `worker` both set `REQUIRED_ENV=REDIS_HOST,QUEUE_KEY` (a
  deliberately explicit, hardcoded requirement in each Deployment's own
  spec -- not sourced from the ConfigMap). `check_required_env()` in
  `app.py` sees `QUEUE_KEY` never resolved and calls `sys.exit(1)` before
  binding a socket -> real `CrashLoopBackOff` (confirmed live: reaches
  `CrashLoopBackOff` on both within ~25-30s of a fresh apply). Symptom A:
  `api`'s Service has zero healthy endpoints, `/readyz` unreachable
  through it -- "the API is down," the paging signal.
  Symptom A': `worker` crash-looping means nothing ever calls `blpop` --
  no direct app-level signal (worker's own `/metrics` is unreachable
  while it's down), but it's *why* symptom B below happens.
- `producer`'s own `REQUIRED_ENV=REDIS_HOST` (only) is deliberately
  lighter -- a real-world "different team, different validation
  standard" asymmetry. It never notices `QUEUE_KEY` is missing, starts
  fine, and `env_str("QUEUE_KEY", "sandbox20:queue")` falls back to the
  app's own hardcoded default. It pushes into `sandbox20:queue` forever.
  Symptom B: the queue key grows unboundedly (confirmed live: `llen
  sandbox20:queue` went 104 -> 200+ within about a minute of an idle
  producer @ `RATE_PER_S=3`, worker down the whole time) -- silent,
  discoverable only via `redis-cli` directly against the queue, not via
  any single app's own logs/metrics (worker, the one component that would
  normally report `app_queue_depth`/`app_processed_total`, is the thing
  that's down).

This is exactly the "one root cause, >=2 independently-diagnosable
symptoms, different failure signatures (loud crash vs. silent
degradation)" shape the design doc asked for, and it converges cleanly:
once `pipeline-config`'s `QUEUE_KEY` is corrected and `api`/`worker`/
`producer` are rolled to pick up the fresh value, `producer` and `worker`
naturally agree on the same corrected key (`t11:jobs` in my reference
fix) with no separate reconciliation step needed.

## Checkpoint split rationale

Two checkpoints, not three -- per the task brief's "fold into cp1 if a
separate hardening checkpoint isn't genuinely valuable":

- `validate_cp1.py`: seed -> confirm broken non-vacuously (CrashLoopBackOff
  on api+worker AND redis queue key visibly growing) -> apply
  `src/pipeline-config-fix.yaml` -> rollout-restart api/worker/producer ->
  assert healthy target (Deployments available, no CrashLoopBackOff,
  `/readyz` green through Service `api`, `worker`'s own
  `app_processed_total` actually rising) -> a durability fold-in: scale
  api+worker to 0 and back to their original replica counts, re-assert the
  same healthy target against fully fresh pods. This last step is the
  "hardening" checkpoint's job folded into cp1 rather than split out --
  it's cheap (~20-30s), meaningfully proves the fix lives in the
  ConfigMap/Deployment objects rather than one lucky pod instance, and
  didn't need a separate re-seed of a different fault variant to be
  valuable.
- `validate_cp2.py`: `INCIDENT.md` doc-gate (5 sections, `check_sections`
  + a `check` for >=3 of 4 grounding keywords: ConfigMap/envFrom/
  REQUIRED_ENV/CrashLoopBackOff) then re-runs `validate_cp1.py` as a real
  subprocess and requires exit 0.

Fix delivery mechanism: `src/pipeline-config-fix.yaml`, a single
learner-edited ConfigMap manifest applied with `kubectl apply -f` on top
of the seeded broken one. This keeps the validator fix-path-agnostic in
the sense the design doc cares about (indifferent to which specific
strategy the learner used to arrive at the correct key/value -- the
validator only ever inspects the resulting live cluster state, never the
learner's reasoning or intermediate steps) while still giving the
validator something concrete and idempotent to `kubectl apply`. The
stock/unfilled stub is comment-only (mirrors task 02's
`src/deployment.yaml` convention) -- `kubectl apply -f` on it fails
immediately with `error: no objects passed to apply`, which is itself a
clean single `NOT PASSED` line via `harness.common.kubectl`'s own
`check=True` path, no extra plumbing needed.

## Image note: redis

`redis:7-alpine` (already on the authoring host's docker from task 07's
work) could NOT be `kind load docker-image`-ed or `kind load
image-archive`-ed into this cluster -- both failed identically:

```
ctr: rpc error: code = NotFound desc = content digest sha256:...: not found
```

Root cause: the image on disk carries full OCI multi-platform
manifest-list metadata, including a `linux/unknown` **build-provenance
attestation** manifest entry, whose blob was never actually pulled to the
local content store (Docker only fetches blobs for the platform you
actually use). `kind load` always invokes `ctr images import
--all-platforms`, which then tries to import every manifest-list entry
including the attestation one and fails on the missing blob. This
reproduced identically even after `docker pull --platform linux/amd64
redis:7-alpine` (Docker Desktop's containerd-backed image store still
retains the full index) and even after a fresh `docker build --platform
linux/amd64` with default BuildKit settings (which attaches its own
provenance attestation by default).

**Fix**: rebuild a clean single-manifest image with attestations
explicitly disabled:

```bash
docker build --platform linux/amd64 --provenance=false --sbom=false \
  -t redis:t11-repack -f Dockerfile.redis-repack .   # FROM redis:7-alpine
kind load image-archive <(docker save redis:t11-repack) --name sandbox20
# (in practice: docker save to a tar file first, then kind load image-archive <tar>)
```

This produced a single-manifest image (`docker image inspect` showed
`linux/amd64` directly, no manifest-list) that `kind load image-archive`
imported cleanly on all three nodes on the first try. Verified live: a
throwaway Pod using `redis:t11-repack` reached Ready and answered `PING`
-> `PONG` inside the cluster. The image content itself is bit-identical
to stock `redis:7-alpine` (same config-layer digest,
`487efc0616382465781b8fdc3d6d1db449e6fd80ae23bf48432a2da6b6929908`) --
only the manifest-list wrapper differs. `given/redis.yaml` uses
`redis:t11-repack`; this is documented in the task README so a learner
doesn't wonder why the image tag doesn't match the module's usual
`redis:7-alpine` (used by task 07's `given/`, which is read-only
reference material there and never actually applied to a live cluster in
that task, so it never hit this problem).

The `redis:t11-repack` image remains `kind load`-ed on all three
`sandbox20` nodes (confirmed via `crictl images` on each node after
cleanup) -- this persists across this task's namespace being deleted,
same as the module's other pre-loaded images. The host-side docker image
tag and scratch Dockerfile were removed after verification; only the
in-cluster containerd copy is needed for the task to keep working.

## Live verification log

1. **Stock (unfilled) run**:
   - `uv run python tests/validate_cp1.py` ->
     `NOT PASSED: kubectl apply -f src/pipeline-config-fix.yaml failed: error: no objects passed to apply`
     (exit 1, single line, no traceback). This run reached that point only
     after the seed+non-vacuous-broken-state confirmation already
     succeeded (CrashLoopBackOff on api+worker within ~30s, queue growth
     confirmed), so the fixture itself was proven live and reproducible
     before the stub's stock failure was hit.
   - `uv run python tests/validate_cp2.py` ->
     `NOT PASSED: section 'Symptoms observed': still contains a placeholder marker -- fill this in`
     (exit 1, single line, no traceback).

2. **Reference pass-path** (throwaway fix, never committed):
   - `src/pipeline-config-fix.yaml` temporarily filled with a correct
     ConfigMap (`REDIS_HOST: redis`, `REDIS_PORT: "6379"`,
     `QUEUE_KEY: t11:jobs`).
   - `INCIDENT.md` temporarily filled with a full grounded writeup.
   - `uv run python tests/validate_cp1.py` ->
     `PASSED: pipeline restored: all Deployments available, no CrashLoopBackOff, /readyz green through Service api, queue draining end to end, fix survives a full scale-to-zero-and-back`
   - `uv run python tests/validate_cp2.py` ->
     `PASSED: INCIDENT.md filled (5 sections, grounded concepts: ['ConfigMap', 'envFrom', 'REQUIRED_ENV', 'CrashLoopBackOff']); CP1 still passes`
   - sha256 of both learner-editable files recorded BEFORE the reference
     fix, files reverted via the saved backup copies, sha256 recomputed
     and confirmed byte-identical:
     - `src/pipeline-config-fix.yaml`:
       `47531e85110c4a89346383e4cb62fb2492ded3af944cfbd630e26ee823f3a6bc`
     - `INCIDENT.md`:
       `617c4bb12c3138e251c0ab1d0caf908507aa06b886e962bae4251ecbf9840dba`
   - Post-revert, both validators re-run and confirmed to fail cleanly
     again with the same `NOT PASSED` lines as step 1.
   - No reference solution committed anywhere in the task directory or in
     this notes file's own history (this file states the fix's *shape*
     for calibration purposes only, not a value to paste).

3. **Cleanup**: namespace `t11` deleted (`--wait=false`) after every run.
   Confirmed absent via `kubectl get ns` at the end of the session. Host
   scratch files (`.tar`s, throwaway `Dockerfile.redis-repack`, sha256
   backup copies) removed from the scratchpad dir; host-side
   `redis:t11-repack` docker tag removed (the in-cluster copy is what the
   task actually depends on and was left in place).

## Calibration numbers used

- `producer` `RATE_PER_S=3`, `worker` `PROCESS_MS=200` (-> 5 items/s max
  drain per replica) -- producer rate comfortably under one worker
  replica's drain capacity, so once fixed the queue actually drains
  instead of merely "not growing as fast." Chosen the same way task 07's
  dev/prod rate contract was: `RATE_PER_S < replicas * (1000/PROCESS_MS)`
  with real headroom.
- CrashLoopBackOff appears reliably within ~25-30s of a fresh apply
  (`REQUIRED_ENV` fails before any startup delay, kubelet's own backoff
  reaches `CrashLoopBackOff` after the first restart) -- `SEED_TIMEOUT_S
  = 90` in the validator is a generous safety margin, not a tuned number.
- Durability check (scale to 0, back up) adds roughly 30-45s to a full
  cp1 run in practice; `DURABILITY_ROLLOUT_TIMEOUT_S = 90` is again a
  safety wrapper.
