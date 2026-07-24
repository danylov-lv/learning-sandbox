{{/*
TODO(you): chart-wide template helpers.

Define at least these two named templates:

  worker.fullname
    A release-name-prefixed resource name, truncated to 63 characters,
    trailing "-" trimmed. This is the standard shape every `helm create`
    scaffold ships with (read one for reference if you want -- run
    `helm create /tmp/scratch-ref` somewhere outside this repo and look at
    its generated `_helpers.tpl` -- but write this one yourself instead of
    copying it in; the point of this task is understanding the pattern,
    not pasting it).

  worker.labels
    The standard label set every resource in this chart applies. Must
    include at least:
      app.kubernetes.io/name
      app.kubernetes.io/instance
      helm.sh/chart

Every template in templates/ should name its resource via
`include "worker.fullname" .` and label it via `include "worker.labels" .`
(or `| nindent N`, however you wire it) -- consistency here is exactly
what the validator checks first.
*/}}
