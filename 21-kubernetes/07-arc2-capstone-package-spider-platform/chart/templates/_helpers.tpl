{{/*
TODO(you): standard Helm name/label helpers, used by every template in
this chart. See README.md "Chart contract" for exactly what's graded.

Expected defines (standard `helm create` shape -- look it up if unfamiliar
rather than guessing field names):

  "spider-platform.name"         -- chart name, honoring .Values.nameOverride
  "spider-platform.fullname"     -- release+chart name, honoring
                                     .Values.fullnameOverride, truncated to
                                     63 chars. EVERY resource's metadata.name
                                     in this chart must start with this.
  "spider-platform.labels"       -- the full label block (includes the
                                     selector labels below plus
                                     helm.sh/chart and app.kubernetes.io/managed-by)
  "spider-platform.selectorLabels" -- app.kubernetes.io/name +
                                     app.kubernetes.io/instance ONLY (used
                                     in both metadata.labels and
                                     spec.selector.matchLabels)

On top of the standard labels above, every resource in this chart also
carries a per-component label the validators select on:

  app.kubernetes.io/component: target | queue | producer | workers

Consider a small helper that takes a component name and returns
"spider-platform.labels" merged with that one extra label, so every
template file calls one helper instead of repeating the merge.
*/}}
