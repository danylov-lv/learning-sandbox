# Hint 2

**`worker.fullname`** -- this is the exact mechanism `helm create`'s
scaffold uses (go read one if hint 1's suggestion still hasn't clicked):
prefer `.Values.fullnameOverride` if the caller set one; otherwise, if the
chart name is already a substring of the release name (true for this task
-- release `t04-worker` already contains `worker`), just use the release
name as-is; otherwise concatenate `<release>-<chart-name>`. Either way,
truncate to 63 characters and trim a trailing `-` (DNS label length limits
on the resulting object name). Since our release name already contains the
chart name, the "contains" branch is the one that actually fires here --
worth tracing through by hand once so the truncate/trim logic isn't cargo
culted.

**`worker.labels`** -- a fixed block of `key: value` lines rendered with
`include ... | nindent N` at every call site. At minimum wire
`app.kubernetes.io/name` (usually the fullname or chart name),
`app.kubernetes.io/instance` (`.Release.Name`), and `helm.sh/chart`
(chart name + version, some separator). Adding `app.kubernetes.io/managed-by:
{{ .Release.Service }}` too is common practice, not required by the
validator.

**The pod template's own labels** need to match whatever the Service's
`selector` uses. Simplest: reuse `worker.labels` for both the pod template
and the selector. More correct (and what `helm create` actually does):
split out a `worker.selectorLabels` helper containing only the
`name`/`instance` pair, used for `spec.selector.matchLabels`, the pod
template's labels, AND the Service's selector -- leaving the full
`worker.labels` (including `helm.sh/chart`, which changes on every version
bump) off the Deployment's *selector* specifically, since that field is
immutable once the Deployment exists.

**checksum/config** -- Helm ships a `sha256sum` template function (Sprig).
`$.Template.BasePath` gives you the current chart's `templates/` directory
regardless of which file this gets evaluated from. Combine `include` with
a `print`-built path to that directory plus `"/configmap.yaml"` to render
the ConfigMap template as a string, from inside the Deployment template,
and pipe that string through `sha256sum` into a pod-template annotation.
Any change to `.Values.config.greeting` changes the rendered ConfigMap
text, which changes the hash, which changes this one annotation --
`spec.template.metadata.annotations` is part of the pod template spec, so
changing it alone is enough to force a rollout even though nothing else on
the Deployment changed.

**REQUIRED_ENV** -- don't write this as one fixed string. Build a list
that always starts with `CONFIG_GREETING`, then conditionally grows to
include `APP_SECRET_TOKEN` depending on `.Values.secret.enabled` (Sprig's
`list`/`append` work inside a template, assigned to a `$variable`), then
join the final list with a comma for the env var's literal value.

**extraEnv** -- `.Values.extraEnv` is a MAP (e.g. `{APP_FOO: bar}`), not a
list. The two-variable form of `range` (`range $key, $value := ...`) gives
you both per iteration, which is what lets you emit one `env:` entry per
key without knowing the key names in advance.
