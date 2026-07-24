# Authoring notes -- 05-chart-advanced-deps-hooks-diffing

Empirics from building/verifying this task. Not learner-facing.

## Gotcha: a fresh `helm install`'s pre-install hook cannot reach a
dependency's own resources -- they don't exist yet

This is the load-bearing discovery of this task. Naive design: queue-chart
(the given dependency) ships a perfectly normal Deployment+Service for
redis; the parent's `queue-init` hook (`pre-install,pre-upgrade`) tries to
`RPUSH` into it. On the very first `helm install` into a clean namespace,
this fails every time with `socket.gaierror: ... Temporary failure in name
resolution` -- the redis Service's DNS name doesn't resolve because the
Service doesn't exist yet.

Root cause, confirmed empirically (not just from docs): Helm's pre-install
phase runs and fully completes *before Kubernetes creates any of the
release's normal (non-hook) resources* -- including a dependency
subchart's own Deployment/Service. This holds regardless of the
`pre-upgrade` half of the annotation (which would work fine on a
subsequent upgrade, since redis already exists by then) -- the task
requires the whole chain to prove out on a first install into `t05`, so
"it works on upgrade" isn't good enough.

Fix: `given/queue-chart/templates/redis.yaml`'s Deployment and Service are
*themselves* annotated as `pre-install,pre-upgrade` hooks, at
`hook-weight: "-20"` -- lower (earlier) than the parent's `queue-init` hook
at `"-5"`. Helm executes hooks within a phase in ascending weight order,
waiting for each to be ready/complete before the next fires, so redis
gets created and becomes ready *before* `queue-init` ever runs, all still
within the pre-install phase, all still before the worker Deployment
(a genuinely normal resource) is created. This is a real, if slightly
obscure, Helm pattern for exactly this "a hook needs something that isn't
up yet" problem.

Consequence worth flagging for future readers: resources carrying
`helm.sh/hook` annotations are tracked entirely outside the release's
normal manifest inventory. That means `helm uninstall` -- which only
touches the tracked manifest -- does **not** remove them, no matter what
`hook-delete-policy` you give them (delete-policy only governs
before-creation/after-success/after-failure cleanup of that hook itself,
never "on release uninstall"). So after this task's live install/uninstall
cycle, redis's Deployment/Service are still sitting in `t05` even though
the release is gone. Gave redis's hook annotations
`hook-delete-policy: before-hook-creation` (only -- no `hook-succeeded`,
that would delete redis right after it starts, before anything gets to use
it) so a *second* install/upgrade attempt cleans up the stale copy before
creating a fresh one, avoiding "already exists" errors across repeated
manual `helm install`/`uninstall` cycles during learner iteration. The
validator doesn't care either way since it force-deletes the whole
namespace before and after every run, but this is exactly the kind of
surprise a learner running this chart by hand would hit and should
understand, not something to quietly paper over -- left a comment in
`redis.yaml` pointing at it.

## Gotcha: string-matching "redis" in a manifest false-positives on the
worker's own `QUEUE_BACKEND=redis` env var

First cut of `_check_template_conditional`'s "did the dependency actually
render" check searched `yaml.dump(doc).lower()` for the substring
`"redis"`. That's also true of the *worker's own* Deployment, which sets
`QUEUE_BACKEND` to the literal string `"redis"` regardless of whether
`queue.enabled` is true or false -- so `--set queue.enabled=false` never
looked like it disabled anything, even when it correctly did. Fixed by
checking a structural signal instead: `metadata.labels["app.kubernetes.io/
name"] == "queue-chart"` (first choice) or a container `image` field
starting with `redis:` (fallback for the Deployment case) -- both are
properties only the *dependency's own* resources have, independent of
what literal strings appear in the parent's env vars.

## Gotcha: Kubernetes event/status timestamps are second-resolution

Proving "hook Job completed before the app pod was created" by comparing
`hook_time < pod_created` (strict) intermittently failed with identical
timestamp strings on both sides -- both timestamps only carry
second-precision (`...T11:52:42Z`), and on this fast a cluster (images
already `kind load`ed, no pull time) the hook completing and the pod being
created can legitimately land in the same wall-clock second. Relaxed to
`<=`; the actual ordering guarantee comes from Helm's hook semantics
(pre-install hooks always finish before any non-hook resource is created),
not from winning a timestamp race, so `<=` is not a loosened assertion --
it's the correct one for the resolution available.

## Gotcha: the hook Job itself is usually gone by the time you'd `kubectl
get` it

`hook-delete-policy: before-hook-creation,hook-succeeded` deletes the
`queue-init` Job immediately upon success -- as part of the *same*,
synchronous `helm install` call, well before that call returns. Polling
`kubectl get job queue-init` from a background thread concurrently with
the blocking `helm install` subprocess sometimes catches its
`status.completionTime` and sometimes doesn't (pure timing luck). Primary
signal ended up being Kubernetes Events instead: Event objects are not
owned by the Job they describe (no ownerReference back to it), so they
survive the Job's deletion; a `reason: Completed` Event against
`involvedObject.{kind: Job, name: queue-init}` is a reliable, non-racy
source for the completion instant. Kept the background-thread poll too, as
a (rarely-needed) faster primary source when it happens to win the race.

## Live verification performed

1. Stock (stub) chart: `uv run python tests/validate.py` from the task
   dir -> single line `NOT PASSED: chart/Chart.yaml has no entries under
   'dependencies' -- add the queue-chart subchart dependency (see
   README.md 'What's required' step 1)`, exit 1, no traceback. This is the
   very first check in the validator (pure YAML parse of Chart.yaml, no
   helm/kubectl invocation yet), so it's unaffected by anything in the
   still-TODO template stubs.
2. sha256 of all 13 task files captured before writing a throwaway
   reference over the stub files in place (`chart/Chart.yaml`,
   `chart/templates/{deployment,service,hook-job}.yaml`, plus
   learner-created `chart/values-dev.yaml`/`values-prod.yaml` and a filled
   `DIFF.md`).
3. `helm dependency build` succeeded; `helm template` default vs.
   `--set queue.enabled=false` verified structurally (redis present/absent,
   hook annotations correct); `values-dev.yaml`/`values-prod.yaml` renders
   verified to actually differ; `DIFF.md` doc gate passed.
4. Full live run twice (separately, both from a completely fresh `t05`):
   `PASSED: queue-chart dependency wired correctly, hook 'queue-init' ran
   and completed before the worker pod existed, redis + worker Ready,
   seeded queue drained to 0 via the running app, hook Job absent after
   uninstall, DIFF.md documents a real dev/prod render diff`, exit 0, total
   wall time ~17-19s per run.
5. Confirmed namespace `t05` and helm release `t05-stack` both gone after
   each passing run (`Terminating` immediately, background-deleted).
6. Reverted all reference-only edits back to stub content each time;
   `sha256sum` diff against the pre-reference baseline showed **zero**
   differences on the second (final) round -- every learner-facing file
   byte-identical to its originally-authored stub/template state.
   `given/queue-chart/templates/redis.yaml` (gained the pre-install hook
   annotations described above) and `tests/validate.py` (the two bugfixes
   above) are the two files whose *final* content legitimately differs
   from the very first draft -- both are authored deliverables, not
   reference-solution leakage.
7. Removed `chart/charts/*.tgz`, `chart/Chart.lock`, and stray
   `__pycache__/` directories created by `helm dependency build`/pytest
   during authoring; `chart/charts/` is covered by this task's own
   `.gitignore`. Re-ran the stock validator once more post-cleanup --
   identical single `NOT PASSED` line as step 1.
8. `git status --short --untracked-files=all -- 20-kubernetes/
   05-chart-advanced-deps-hooks-diffing` shows exactly the 17 authored
   deliverable files, nothing else.
