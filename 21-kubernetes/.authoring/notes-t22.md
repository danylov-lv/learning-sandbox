# Authoring notes -- task 22 (operator-kopf-scrapejob)

## CRD schema chosen

Group `sandbox20.dev`, version `v1`, kind `ScrapeJob`, plural `scrapejobs`,
singular `scrapejob`, namespaced. `spec` has exactly three properties,
all with CRD-level defaults so a minimal CR (`{}` spec) is still valid:

- `replicas`: integer, minimum 1, default 1
- `image`: string, default `sandbox20-app:1.0`
- `processMs`: integer, minimum 1, default 100

Child Deployment label contract (validator-selected, not name-selected):
`app.kubernetes.io/managed-by: scrapejob-operator` + `scrapejob-name: <CR
name>`. Worker container: fixture app in `WORK_MODE=server` default (no
queue wiring needed -- this task is about the operator, not the app).

## Stub convention applied to the CRD specifically

`src/crd.yaml`'s stub is NOT the whole-file-comment style used for chart
values files elsewhere in the module -- it's a real `CustomResourceDefinition`
with `metadata.name` filled in and `spec: {}`. This was deliberate: `kubectl
apply` against it produces a clean, multi-bullet Kubernetes API validation
error (`spec.group: Required value`, `spec.versions: ... must have exactly
one version marked as storage version`, etc.) rather than a YAML parse
error -- exactly the "fail validation cleanly" stub convention from
design.md, and a more realistic first failure mode for a CRD specifically
than an all-comment file would give (an all-comment file would instead
fail at "no objects passed to apply", which is a less instructive error
for this particular artifact type).

`_opharness.apply_crd()` surfaces every `*`-prefixed bullet from the API
error (not just `_last_line`), since the CRD validation error is
genuinely multi-line and the LAST line alone (`status.storedVersions: ...
must have at least one stored version`) is one of the least informative
of the bullets.

## Operator-as-subprocess harness approach

`tests/_opharness.py` (shared by all three checkpoints, not itself a
validator):

- Builds a kubeconfig scoped to ONLY the `kind-sandbox20` context via
  `kubectl --context kind-sandbox20 config view --minify --flatten`
  (using `harness.common.kubectl`, which already pins that context) and
  writes it to a temp file. The operator subprocess gets `KUBECONFIG=
  <that file>` in its env -- this is how the operator is pinned at the
  right cluster, since `kopf run` has no `--context`/`--kubeconfig` CLI
  flag at all (checked via `python -m kopf run --help`). Confirmed this
  works: kopf's own `login_via_client` startup activity logs "Client is
  configured via kubeconfig file." and reads whatever `KUBECONFIG` points
  at.
- Spawns `[sys.executable, "-m", "kopf", "run", operator.py, "--namespace",
  "t22", "--verbose"]` -- NOT `uv run python -m kopf ...`. `sys.executable`
  inside a script already running via `uv run python tests/validate_cpN.py`
  is already the venv's real `python.exe` (verified), so this avoids
  adding an extra `uv` launcher layer on top of an already-real interpreter.
- stdout+stderr redirected to a real log FILE (not a `PIPE`) opened before
  `Popen`, so there's no risk of a Windows pipe buffer filling and
  deadlocking the operator while this process is busy elsewhere (kopf
  with `--verbose` is chatty). The validator polls the file's text
  directly for the "started watching" marker and later greps it for
  reconcile-summary lines.
- Startup readiness marker: kopf logs `Starting the watch-stream for
  scrapejobs.v1.sandbox20.dev in 't22'.` once it's actually watching --
  confirmed present at DEBUG level (shown because `--verbose` is passed).
  This is what `Operator.start()` polls for, not a fixed sleep.
- Reconcile-event grep targets are kopf's OWN framework-level summary
  lines, not anything the learner's handler needs to log itself:
  `Creation is processed: 1 succeeded; 0 failed.` / `Updating is
  processed: 1 succeeded; 0 failed.` / `Deletion is processed: 1
  succeeded; 0 failed.`, each scoped with a `[t22/<cr-name>]` prefix. These
  appear at INFO level the moment a handler for that lifecycle event
  returns without raising -- independent of the handler's function name or
  any logging the learner adds. Confirmed all three empirically against a
  throwaway reference operator (create/update/delete cycle, full log
  captured during authoring).

## Windows subprocess gotchas (confirmed empirically, not just read about)

- `python -m kopf run <file> --namespace t22 --verbose` spawns a SECOND,
  genuinely separate child `python.exe` process with the identical command
  line one level down (confirmed via `Get-CimInstance Win32_Process` --
  parent PID X running `-m kopf run ...`, child PID Y running the exact
  same argv). Root cause not fully pinned down (kopf's own internal use of
  `multiprocessing`/a worker process is the leading hypothesis; not an
  artifact of `uv run` or of git-bash's job control -- reproduced
  identically spawning directly from a Python `subprocess.Popen` with no
  bash backgrounding involved at all).
- Despite that, `proc.terminate()` (`CREATE_NEW_PROCESS_GROUP` at spawn
  time, matching `harness.common.port_forward`'s existing pattern) on just
  the immediate child reliably reaps the grandchild too in this setup --
  verified via a standalone spawn/sleep/terminate test script plus a
  `Get-Process` sweep immediately after, twice, no orphan `python.exe`
  left behind either time. `Operator.stop()` still falls back to `kill()`
  after a 10s `wait()` timeout as a safety net, but it was never needed in
  testing.
- kopf logs `OS signals are ignored: can't add signal handler in Windows.`
  at startup on this platform -- i.e. kopf itself cannot react to
  SIGINT/SIGTERM-style signals here at all. This makes `Popen.terminate()`
  (which maps to `TerminateProcess`, a hard kill, not a caught signal) the
  ONLY viable way to stop it on Windows; there is no graceful-shutdown
  path to rely on, which is fine since the validator doesn't need one.

## Cleanup race found and fixed

First full CP3 run (chains CP1 then CP2 as subprocesses back-to-back)
failed with a real bug, not a learner-facing one: CP1's teardown deleted
namespace `t22` with `--wait=false` (fire-and-forget), so CP2 started
while `t22` was still `Terminating`, and its `kubectl apply` of the
ScrapeJob CR failed with `... is forbidden ... because it is being
terminated`. Fixed by making `full_cleanup()` block (`--wait=true`,
generous 90s/60s timeouts) on both the namespace and CRD deletion --
mirrors task 07's `delete_ns(NS, wait=True)` precedent. Re-ran CP3 clean
after the fix. This also matters for a learner manually re-running
checkpoints back-to-back by hand, not just for CP3's subprocess chaining.

Also confirmed separately: a stub operator (`on_delete` raising
`NotImplementedError` forever) would otherwise wedge `t22`/the CRD in
`Terminating` permanently, because kopf's own finalizer on the ScrapeJob
CR is never removed. `strip_finalizers()` (`kubectl patch scrapejob
<name> --type=merge -p '{"metadata":{"finalizers":[]}}'`) runs before
every namespace/CRD delete in `full_cleanup()`, unconditionally, so
cleanup never depends on the operator (stub or reference) having ever
successfully reconciled a delete.

## Checkpoint split

- **CP1** (`validate_cp1.py`): CRD apply + operator start + one CR
  (`replicas: 2`) -> exactly one labeled child Deployment reaching 2/2
  ready, plus a successful create-reconcile log line. Stub fails at the
  CRD-apply step already (see above); with a valid CRD but stub handlers
  it instead fails at the `wait_until` (confirmed both failure modes
  separately during authoring -- see "Verify live" below).
- **CP2** (`validate_cp2.py`): CR at `replicas: 1` -> patch to `replicas:
  3` (asserts the Deployment's `uid` is unchanged -- proves patch, not
  delete+recreate) -> delete CR -> asserts the Deployment disappears ->
  greps for successful update AND delete reconcile log lines.
- **CP3** (`validate_cp3.py`): `DESIGN.md` doc-gate (5 sections via
  `check_sections`, plus a grounding check requiring >=2 of
  `finalizer`/`scrapejob-name`/`idempotent` to appear, so the answer has
  to be about this operator specifically), then re-runs CP1 and CP2 as
  real subprocesses and requires both to still exit 0.

## Stock-fail lines (stub `src/crd.yaml` + `src/operator.py`, as committed)

```
$ uv run python tests/validate_cp1.py
NOT PASSED: kubectl apply -f src/crd.yaml failed: * metadata.name: Invalid value: "scrapejobs.sandbox20.dev": must be spec.names.plural+"."+spec.group; * spec.group: Required value; * spec.scope: Required value; * spec.versions: Invalid value: []apiextensions.CustomResourceDefinitionVersion(nil): must have exactly one version marked as storage version; * spec.names.plural: Required value; * spec.names.singular: Required value; * spec.names.kind: Required value; * spec.names.listKind: Required value; * status.storedVersions: Invalid value: []string(nil): must have at least one stored version
(exit 1)

$ uv run python tests/validate_cp2.py
(same CRD-apply failure line; exit 1)

$ uv run python tests/validate_cp3.py
NOT PASSED: section 'The reconcile loop, in your own words': still contains a placeholder marker -- fill this in
(exit 1)
```

Separately confirmed (with a temporarily-valid reference `crd.yaml` but
still-stub `operator.py`, to isolate the operator layer from the CRD
layer): CP1 fails with `NOT PASSED: timed out after 120s waiting for
exactly one child Deployment labeled scrapejob-name=cp1-crawl to reach 2
ready replicas` -- confirms the create-handler check is non-vacuous
independent of the CRD stub also failing cleanly on its own.

## Reference-pass confirmations

With a throwaway correct `src/crd.yaml` + `src/operator.py` (create via
`kopf.adopt` + `AppsV1Api.create_namespaced_deployment`, update via
`patch_namespaced_deployment` on `spec.replicas` only, delete via
`delete_namespaced_deployment` with 404 tolerance) and `DESIGN.md` filled
in:

```
$ uv run python tests/validate_cp1.py
PASSED: child Deployment 'cp1-crawl-worker' appeared with 2/2 ready replicas; operator log shows a successful create reconcile

$ uv run python tests/validate_cp2.py
PASSED: Deployment 'cp2-crawl-worker' reconciled 1->3 replicas in place (uid unchanged) then removed on CR deletion; update and delete reconciles both logged

$ uv run python tests/validate_cp3.py
PASSED: DESIGN.md filled (5 sections, grounded concepts: ['finalizer', 'scrapejob-name', 'idempotent']); CP1 and CP2 both still pass
```

All three exit 0.

## sha256 revert confirmation

sha256 of every stub/template file was captured before any reference
content was written in place, and again after reverting. `diff` between
the two listings showed differences ONLY in `__pycache__/*.pyc` (deleted
after, not part of the repo) and `tests/_opharness.py` (a genuine bugfix
made during authoring -- the blocking-cleanup fix above -- kept
intentionally, not reverted). `README.md`, `DESIGN.md`, `NOTES.md`,
`src/crd.yaml`, `src/operator.py`, all three `hints/*.md`, and
`tests/validate_cp1.py`/`validate_cp2.py`/`validate_cp3.py` are all
confirmed byte-identical pre/post. No reference solution was committed.

Final state verified clean: no `t22` namespace, no `scrapejobs.sandbox20.dev`
CRD, no lingering `python.exe`/kopf subprocess, no `__pycache__` left in
the task directory.
