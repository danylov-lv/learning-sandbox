# Authoring notes -- 04-first-chart-from-manifests

Empirics from building/verifying this task. Not learner-facing.

## Gotcha: `{{ }}` inside `#`-comment stub files is NOT inert

The stub convention says templates ship with a `# TODO(you): ...` comment
block that "renders into nothing". That's true for plain YAML comments --
but Helm's template engine (Go templates) parses `{{ ... }}` actions
*before* anything is treated as YAML, so a literal `{{ .Values.x }}`
written inside prose inside a `#` comment still gets executed. Writing
"wrap this in `{{- if .Values.secret.enabled }}` / `{{- end }}`" as
descriptive text inside `secret.yaml`'s TODO comment caused `helm lint` to
fail with `nil pointer evaluating interface {}.enabled` on the STOCK chart
(before the learner touches anything), instead of the clean structural
"no Deployment found" failure the stub convention wants.

Fix: describe Go-template mechanics in stub comments using prose ("a
Go-template if action", "interpolated, not literal") instead of literal
`{{ }}` syntax. The one safe exception is a real Go-template comment block
(`{{/* ... */}}` in `_helpers.tpl`) -- that syntax is inert by
construction (the template engine's own comment mechanism), so it can
safely mention `.Values`/`include` by name inside it without executing
anything.

Lesson for future stub authoring in this module: grep every stub file for
literal `{{` before considering it "renders to nothing" -- `helm lint`/
`helm template` on the stock chart is the only way to actually confirm it,
reading the file isn't enough.

## Helm fullname resolution for this release/chart name pair

Release name is fixed as `t04-worker` (repo-wide rule), chart name is
fixed as `worker` (task spec). The standard `<chart>.fullname` helper's
"does the release name already contain the chart name" branch fires here
(`t04-worker` contains `worker`), so the reference implementation's
fullname resolves to exactly `t04-worker` for every resource -- no
`-worker` suffix gets appended. All resources (Deployment/Service/
ConfigMap/Secret) end up with the identical literal name `t04-worker`,
which is valid: Kubernetes identity is (namespace, kind, name), so
same-name-different-kind objects don't collide. The validator checks
`name.startswith(RELEASE)` rather than requiring a literal trailing `-`,
specifically to accommodate this (a hyphen-suffixed variant, e.g. from a
custom `worker.fullname` that doesn't use the "contains" shortcut, would
also pass).

## Validator design choices worth remembering

- `CONFIG_GREETING`'s expected value in the LIVE section is read from the
  live ConfigMap object itself (via the Deployment's own
  `configMapKeyRef.name`/`key`), not from a value the validator assumes in
  advance by parsing `values-dev.yaml`. This keeps the check honest against
  whatever key name the learner chose inside the ConfigMap's `data:` block
  -- only the env var name (`CONFIG_GREETING`) and the wiring mechanism
  (`configMapKeyRef`) are part of the contract, not the ConfigMap's
  internal key name.
- `REQUIRED_ENV` adaptation (must include `APP_SECRET_TOKEN` only when
  `secret.enabled` is true) is checked structurally (via `helm template`)
  BEFORE the live section, so a learner who gets this wrong sees a precise
  "REQUIRED_ENV lists APP_SECRET_TOKEN but secret.enabled is false" message
  instead of just watching the live rollout hang/crash-loop with a less
  obvious signal.
- LIVE section wraps `ensure_ns`..`helm uninstall`/`delete_ns` in
  try/finally so a failed assertion mid-way (e.g. rollout timeout) still
  cleans up the namespace and release -- verified by forcing a failure
  path during authoring and confirming `t04` still got deleted.

## Live verification performed

1. Stock (stub) chart: `uv run python tests/validate.py` from the task
   dir -> single line `NOT PASSED: expected a Deployment in the
   bare-defaults render but found none -- chart/templates/ is still a stub
   for it`, exit 1, no traceback. (Initial version of this stub also
   surfaced the `{{ }}`-in-comment bug above as a *different* NOT PASSED
   line from `helm lint`, before the stub text was fixed -- worth
   double-checking after any future edit to stub prose.)
2. Reference implementation written in-place over the stub files
   (sha256 of all 16 task files captured first), full validator run ->
   `PASSED: helm lint clean; fullname/labels/checksum/replicaCount/extraEnv
   wiring verified via helm template; values-dev/values-prod render
   correctly; live install+upgrade in ns t04 succeeded with 3 ready
   replicas after the prod upgrade`, exit 0.
3. Confirmed namespace `t04` and helm release `t04-worker` both gone after
   the passing run (namespace `Terminating` immediately after, fully gone
   within ~10s).
4. Reverted all 8 touched files back to their stub content; `sha256sum -c`
   against the pre-reference baseline confirmed all 16 task files
   byte-identical to what they were before the reference chart was
   written.
5. Re-ran the stock validator once more post-revert -- identical single
   NOT PASSED line as step 1.
6. `git status` on the task directory shows only the expected untracked
   new directory, no stray `__pycache__`/build artifacts.
