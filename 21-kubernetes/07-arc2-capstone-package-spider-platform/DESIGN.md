# Design Review -- Spider Platform Chart

Fill in each section grounded in the chart you actually wrote in `chart/`
and what CP1/CP2 actually observed against it -- not generic Helm advice.
This is graded (`tests/validate_cp3.py`): every section needs real content
past the shipped `[fill in` marker, a minimum length, and the vocabulary of
this specific chart (see hints/hint-3.md if you're unsure what "grounded"
means here).

## What is a value and why

[fill in -- walk through at least three specific entries in `values.yaml`
(name a real path, e.g. `workers.probes.readiness.periodSeconds`) and
defend each one against a real review checklist question: who would ever
need to change this without editing a template, and under what realistic
circumstance? A value nobody would ever plausibly override in `values-dev.yaml`
or `values-prod.yaml` is a value that shouldn't exist -- did any of yours
fail that test once you thought it through?]

## What stays hardcoded and why

[fill in -- name at least one thing in your chart that is NOT a value
(container port 8080, the queue key format, WORK_MODE strings, whatever
you chose) and explain why turning it into a value would add configuration
surface without adding real flexibility. What's the failure mode of a
chart that exposes everything as a value instead of drawing this line
somewhere?]

## Upgrade story

[fill in -- trace exactly what happens, mechanically, when a learner edits
`workers.processMs` and runs `helm upgrade`: which object changes first,
how the checksum annotation on the workers pod template forces a rollout
that Kubernetes would otherwise skip (since the Deployment's own container
spec didn't change), and what would happen on upgrade WITHOUT that
annotation. Also state what your chart guarantees does NOT restart across
a values-dev.yaml -> values-prod.yaml upgrade, and why -- CP2 checks this
concretely against the queue pod.]

## Failure modes

[fill in -- what actually happens to `workers` pods, concretely, if the
`queue` Deployment is scaled to zero while workers are running (trace it
through the app's own redis reconnect/backoff loop in `app/app.py`, not in
the abstract)? What happens to `producer` in the same scenario? Separately:
what happens to `workers`' own readiness if `target` is disabled entirely
-- does anything in your chart's wiring make `workers` depend on `target`
at all, and should it?]

## If this ran in production

[fill in -- name at least three concrete gaps between this chart and a
production-ready deployment of the same platform: what would an HPA on
`workers` need that a fixed `workers.replicas` doesn't give you (forward
reference: task 19), what would a PodDisruptionBudget protect against here
that this chart currently has no defense against at all (forward
reference: task 20), and what would a NetworkPolicy restricting `workers`
to only reach `queue` protect against that an open-by-default cluster
currently does not (forward reference: task 14)? Naming the gap is the
point -- you are not expected to have built any of these three.]
