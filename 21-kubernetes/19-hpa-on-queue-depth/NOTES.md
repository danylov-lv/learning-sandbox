# Notes

This file is graded -- the validator checks that every section below is
present, has every `[fill in]` replaced, and is grounded in real
vocabulary from this task. Write in your own words, using what you
actually observed running the validator (replica counts, timings), not
just restated prompt text.

## The external metrics pipeline

Trace the whole path a number takes from "a message sits in RabbitMQ" to
"the HPA decides to add a replica": what does each of RabbitMQ, Prometheus,
and prometheus-adapter actually do to that number, and why does the
`external.metrics.k8s.io` API need to exist at all instead of the HPA
just asking RabbitMQ directly?

[fill in]

## Why queue depth, not CPU

Argue concretely why a CPU-based HPA would be the wrong tool for scaling
`queue-consumer`, using what you know about what this consumer actually
spends its time doing.

[fill in]

## Scaling observations

What did you actually see when you ran the validator (or your own manual
test)? Replica counts before/during/after, roughly how long the scale-up
took, and what `stabilizationWindowSeconds` you chose for scale-down and
why.

[fill in]

## AverageValue arithmetic

State the `averageValue` you chose in `src/hpa.yaml` and show the
`desiredReplicas = ceil(currentMetricValue / averageValue)` arithmetic for
at least one queue depth you actually observed.

[fill in]
