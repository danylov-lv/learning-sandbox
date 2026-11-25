# Hint 2

**Labels.** The standard `helm create` scaffold defines two label sets for
a reason: `selectorLabels` (name + instance only) go in BOTH
`spec.selector.matchLabels` and the pod template's `metadata.labels`,
because the first is immutable after creation and must always be a subset
of the second. `labels` (selector labels plus `helm.sh/chart` and
`app.kubernetes.io/managed-by`) goes on the resource's own
`metadata.labels`, not the selector. On top of that pair, add your own
per-component label (`app.kubernetes.io/component: workers`, etc.) to
both the resource's own labels AND the selector/pod-template labels for
that one resource -- the validators rely on it being queryable via
`-l app.kubernetes.io/component=workers` against a live pod, not just
present on the Deployment object.

**The queue-name derivation**, concretely: if your `queue-service.yaml`
computes its name as (for example)
`{{ include "spider-platform.fullname" . }}-queue`, then
`producer-deployment.yaml`'s `REDIS_HOST` env entry should render that
exact same template expression -- `value: "{{ include
"spider-platform.fullname" . }}-queue"` -- not a copy-pasted string. If the
expression is identical in both files, renaming the release changes both
outputs together, which is exactly what the validator checks by rendering
under two different release names.

**Resources on `workers`**: `.Values.workers.resources` should be a plain
map (`{}` in `values.yaml`, a real requests/limits block in
`values-prod.yaml`) rendered with `{{ toYaml .Values.workers.resources |
nindent N }}` at the right indent level under the container's
`resources:` key. An empty map renders as `resources: {}`, which is valid
YAML and a legitimate Deployment (no resources set) -- exactly what
`values.yaml`'s default should do, since only `values-prod.yaml` is
required to set real numbers.

**Probes**: every numeric field under `workers.probes.readiness` and
`workers.probes.liveness` needs its OWN `{{ .Values... }}` reference in
the template. It's tempting to hardcode `periodSeconds: 5` because that's
what you're defaulting it to in `values.yaml` -- don't; the validator
overrides it with `--set` and checks the number that comes out changed
too.
