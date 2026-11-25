# Hint 1

Direction, not YAML yet.

You are writing three Kubernetes objects that all have to agree about one
thing: **the pod label set**. The Deployment stamps labels onto its pod
template; the HPA points at the Deployment by *name*; the PDB selects pods by
*label*. If any of those three disagree — a typo in a label, an HPA name that
doesn't match the rendered Deployment name — the manifest still renders and
`helm lint` still passes, but the HPA scales nothing and the PDB protects
nothing. Decide your naming/label scheme ONCE before you write a template.
A `_helpers.tpl` named template that emits the label block, `include`d in all
three files, is the way to guarantee they never drift.

Two objects here you may not have hand-written before: a
`HorizontalPodAutoscaler` (`autoscaling/v2`) and a `PodDisruptionBudget`
(`policy/v1`). Start from the API reference for each, not a generated
scaffold — the whole point of this bonus is that you can defend every line.

Everything you need is already in `values.yaml`; you are not inventing knobs,
you are consuming them. Render early and often: `helm template k8s-bonus/chart`
prints exactly what k8s would receive.
