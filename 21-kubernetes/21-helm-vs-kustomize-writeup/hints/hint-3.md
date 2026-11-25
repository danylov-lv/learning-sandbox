# Hint 3

If you get stuck on a specific dimension, these are the ones actually
worth reading up on before writing about them (see `README.md`'s "Topics
to read up on" for the full list) -- pick whichever ones your answer is
currently thin on:

- The `checksum/config` / `checksum/secret` pod-annotation convention is
  a Helm *chart-author* convention, not something Helm does for you
  automatically -- it only exists if the chart's own template computes it
  with `sha256sum`/`tpl` over the values. Compare that against what
  Kustomize's `configMapGenerator`/`secretGenerator` do to a generated
  object's *name* when its content changes, and what that name change
  then does to anything referencing it.
- An Argo CD `Application`'s `spec.source` block looks meaningfully
  different depending on whether `spec.source.helm.valueFiles` or
  `spec.source.kustomize.*` is set -- if you have access to a real Argo
  CD `Application` at work (or recall one from arc 5's tasks), compare
  the two shapes directly instead of guessing.
- Helm hooks have weights and deletion policies (`helm.sh/hook-weight`,
  `helm.sh/hook-delete-policy`); Kustomize has no equivalent concept at
  all. That's not a minor gap -- ask what a chart author actually uses
  hooks for, and what the Kustomize-only alternative looks like when you
  need that same behavior (a separate Job, a CI step, a sync-wave
  annotation understood only by the GitOps controller rather than the
  tool itself).
- Chart `dependencies` (subcharts) let a parent chart's `values.yaml`
  reach into a child chart's values via aliasing and `global`; a
  Kustomize `base` has no values-overriding mechanism at all beyond what
  a patch rewrites structurally. That asymmetry is worth naming precisely
  rather than gesturing at "Helm has more features."
