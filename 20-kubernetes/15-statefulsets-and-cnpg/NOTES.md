# Notes

Space for your own observations while working through this task. The
three sections below **are** graded by `tests/validate.py` (structural
check: section present, substantial, no leftover placeholder; keyword
check: your answers are grounded in specific terminology, not just
restating the README) — everything else in this file is free-form and
not graded.

## StatefulSets vs Deployments

[fill in — why does a database need stable identity and a PVC per
replica instead of the anonymous, interchangeable pods a Deployment
gives you? What does "ordered" startup/scale-down buy you that a
Deployment's all-at-once model doesn't? Where does a headless Service
fit into this picture?]

## Failover observations

[fill in — walk through what you actually saw happen, in order, after
you force-deleted the primary pod: which fields changed first
(`status.currentPrimary`? `readyInstances`?), what happened to the
deleted pod's name, how long the cluster took to get back to fully
ready, and what "quorum" has to do with how CNPG decided which replica
to promote.]

## Why databases on Kubernetes are hard

[fill in — in your own words, what makes running a stateful workload
like Postgres on Kubernetes fundamentally harder than running the
stateless app from earlier tasks, and what did an operator like CNPG
actually do for you here that you'd have had to build by hand with a
bare StatefulSet?]

## What I learned

[fill in]

## Gotchas

[fill in]

## Open questions

[fill in]
