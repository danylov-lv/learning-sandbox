# Hint 3

Rough shape per file, not code to paste in -- write the actual YAML/Go
templates yourself, matching your own indentation and quoting choices.

**`configmap.yaml`**

- `kind: ConfigMap`, name + labels from the helpers.
- one entry under `data:` whose value is `.Values.config.greeting` (quote
  it -- Helm's YAML values can render ambiguously unquoted).

**`service.yaml`**

- `kind: Service`, name + labels from the helpers.
- `spec.selector` must match whatever labels you put on the Deployment's
  *pod template* (not the Deployment's own top-level labels) -- reuse your
  labels helper for both, or split out a smaller selector-only helper if
  you want the selector immune to churn in the full label set (think about
  why `spec.selector` on a Deployment is immutable, and what that means if
  a label inside it changes on every chart version bump).
- one port entry: `.Values.service.port` -> `8080` (the container's fixed
  listen port).

**`secret.yaml`**

- wrap the entire resource in a conditional on `.Values.secret.enabled` --
  when it's false, this file should render literally nothing, not an
  empty/malformed Secret.
- `type: Opaque`, one key under `data`/`stringData` holding
  `.Values.secret.token`.

**`deployment.yaml`**

- name + labels (both the Deployment's own metadata and the pod template's
  `metadata.labels`) from the helpers; `spec.selector.matchLabels` needs to
  match the pod template labels too.
- `spec.replicas` from `.Values.replicaCount` -- a plain value reference,
  no hardcoded number anywhere near it.
- a pod-template annotation that hashes the *rendered* ConfigMap contents.
  Helm ships a `sha256sum` Sprig function; you need to render the
  configmap template's text first and pipe that through it -- look up how
  `include` combined with `$.Template.BasePath` lets you render a sibling
  template file by path from inside another template.
- container `resources:` -- pass `.Values.resources` through wholesale
  (there's a Sprig/Helm builtin for dumping an arbitrary values subtree
  back out as YAML at the right indent level; you don't want to enumerate
  `requests`/`limits` by hand here).
- container `env:` list, built from four independent pieces:
  1. `CONFIG_GREETING` via `configMapKeyRef` (always present).
  2. `APP_SECRET_TOKEN` via `secretKeyRef` -- only emitted when
     `.Values.secret.enabled` is true (same conditional as `secret.yaml`).
  3. one entry per key in `.Values.extraEnv` -- it's a map, so the two-
     variable form of `range` gives you both the key and the value per
     iteration.
  4. `REQUIRED_ENV` -- not a fixed string. Build a list starting with
     `"CONFIG_GREETING"`, conditionally append `"APP_SECRET_TOKEN"` when
     secret.enabled is true, then join it with a comma. This has to be
     computed, not hardcoded, or dev (`secret.enabled: false`) crashes on
     startup the moment `check_required_env` finds `APP_SECRET_TOKEN`
     listed but never set.

**`values.yaml` / `values-dev.yaml` / `values-prod.yaml`**

- `values.yaml` needs every key from the contract with a safe, self-
  sufficient default (a bare `helm template chart/` with zero `-f`/`--set`
  should still render a working Deployment) -- go re-read the "Defaults
  safety" section of `given/review-checklist.md` before picking these.
- `values-dev.yaml` only needs to override the handful of keys that
  actually differ from the defaults for dev (replicas, secret off) -- it
  does not need to restate every key from `values.yaml`.
- `values-prod.yaml` overrides replicas up, turns the secret on, and sets
  real `resources`. It should NOT contain a real `secret.token` -- that's
  supplied at install/upgrade time via `--set`, see the README's
  completion criteria for the exact command.
