# Authoring notes -- 07-arc2-capstone-package-spider-platform

Empirics from live verification with a throwaway reference chart (built in
scratch, never committed, reverted byte-identical afterward -- sha256
matched before/after for every file in `chart/` and `DESIGN.md`).

## Gotcha: Go templates parse `{{ }}` inside YAML comments too

The TODO stub template files use `# ...` prose to describe the expected
shape, including snippets like `{{ .Values.target.port }}`. Helm's
rendering pipeline runs the WHOLE file through Go's `text/template` engine
before it even looks at YAML/comment structure -- an unmatched control
action like `{{ if .Values.target.enabled }}` inside a comment, with no
corresponding `{{ end }}` anywhere in that file, produces a real parse
error ("unexpected EOF") rather than being ignored as a comment. Matched
pairs on the same conceptual block (e.g. `{{ if }} ... {{ end }}` both
mentioned in one stub's prose) are fine since the template parses as a
complete, if pointless, if/end block. Fixed by rewording the one place
that had an unmatched `{{ if }}` (`target-service.yaml`'s stub comment) to
describe the guard in plain English instead of literal Go template syntax.
Worth remembering for any future task's YAML-comment TODO stubs living
inside a Helm `templates/` directory specifically (this trap doesn't exist
for plain Kubernetes manifest stubs elsewhere in this module, which are
never routed through a template engine).

## Stub failure modes actually observed (stock, unfilled chart)

- `validate_cp1.py`: `helm lint` fails because `values.yaml` is an
  effectively-empty stub (comments only) and every template references
  `.Values.<component>.*` paths that don't exist -- surfaces as `nil
  pointer evaluating interface {}.replicas` from Helm's own engine, caught
  and reported as a single `NOT PASSED: helm lint ... failed: ...` line.
- `validate_cp2.py`: same nil-pointer error, now via `helm install`
  (`INSTALLATION FAILED: ...`). Confirmed `t07` namespace/`t07-spider`
  release do NOT linger after this failure -- the `finally: cleanup()`
  wrapper runs even though `not_passed()` raises `SystemExit` from inside
  the `try` block (harness's `guarded` explicitly re-raises `SystemExit`
  rather than swallowing it, so `finally` still executes first).
- `validate_cp3.py`: fails immediately on `DESIGN.md`'s first `[fill in`
  placeholder via `harness.check_sections`, before ever touching
  `chart/` or the cluster.

All three: exactly one `NOT PASSED: ...` line, exit 1, no tracebacks.

## Calibration that passed live, with real numbers

`values-dev.yaml`: `workers.replicas: 1`, `workers.processMs: 200` (5
items/s drain capacity), `producer.ratePerS: 2` -- 3/s of headroom.
`values-prod.yaml`: `workers.replicas: 3`, `workers.processMs: 150` (~20
items/s aggregate capacity), `producer.ratePerS: 6` -- comfortable
headroom at both tiers, and since `PROCESS_MS`/`RATE_PER_S` are simulated
sleeps rather than CPU-bound work, this arithmetic is deterministic
regardless of the grading machine's speed.

Live `validate_cp2.py` run against the reference chart: `app_processed_total`
rose by 55 over the ~30s dev window (≈1.83/s -- tracks the producer's 2/s
input rate, meaning workers were supply-limited rather than backed up, as
intended), max observed `app_queue_depth` was 4 (bound checked was 60,
generous). After the `values-dev.yaml` -> `values-prod.yaml` upgrade: 3/3
workers ready, queue pod's `status.startTime` identical before/after
(`2026-07-23T11:54:11Z` in the recorded run), post-upgrade queue depth
sampled well under the 150 bound. Full `validate_cp2.py` wall time
end-to-end (install + 30s window + upgrade + 15s window + uninstall):
~71s. Full `validate_cp3.py` (design doc gate + CP1 subprocess + CP2
subprocess): ~79s.

## Design decisions worth recording

- CP1 deliberately never calls `require_cluster()` -- every check is
  `helm lint`/`helm template` plus parsing rendered YAML offline. This
  keeps CP1 fast and cluster-independent, matching the module's "structure
  first, live behavior second" checkpoint split.
- The validator identifies each of the four components by the mandated
  `app.kubernetes.io/component` label rather than by any assumed resource
  NAME -- this keeps the chart's naming scheme (which helper/fullname
  pattern the learner picks) unconstrained while still giving the
  validator a stable, name-agnostic selector. This label is stated
  up-front in README.md's "Chart contract" section, not a hidden
  requirement discovered only in the validator source.
- The queue-hostname-derivation check (CP1) renders the chart under TWO
  different release names and asserts the queue Service's name AND both
  `producer`/`workers`' `REDIS_HOST` change together between the two
  renders -- this is what actually distinguishes "derived from the
  Service's own rendered name" from "a literal string that happens to
  match by coincidence," which a same-release single render cannot prove.
- `resolve_env()` in both `validate_cp1.py` and (implicitly, via the same
  pattern) `validate_cp2.py`'s live metrics reads supports both a direct
  `env[].valueFrom.configMapKeyRef` and an `envFrom` + `ConfigMap` wiring
  style, since the task README intentionally leaves that choice to the
  learner (only the checksum annotation is required to hash an actual
  ConfigMap, since that's the object the checksum needs to attach to).

## What's NOT covered (by design)

CP2 does not assert continuous zero-downtime HTTP availability through the
prod upgrade (that's task 02's territory) -- it gates structurally on
`readyReplicas == 3` and the queue pod's untouched `startTime` instead, per
the task spec's explicit "do NOT gate on exact rates" instruction.
