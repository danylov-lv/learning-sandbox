# Hint 2

`AverageValue` targets on an `External` metric use one specific formula,
and picking a threshold without knowing the formula is guessing:

```
desiredReplicas = ceil(currentMetricValue / averageValue)
```

There is no implicit division by current replica count and no per-pod
averaging happening on the RabbitMQ side -- `currentMetricValue` is
whatever your `metricsQuery` in the adapter's rule returns as a single
number (here: total messages ready in `sandbox20-queue`, summed), full
stop. So if you set `averageValue: "10"` and the queue has 47 messages
ready, the HPA wants `ceil(47/10) = 5` replicas -- clamped to whatever
`maxReplicas` you chose.

That means your choice of `averageValue` *is* your choice of "how many
queued messages should one consumer be responsible for before I want
another one," in plain numbers you can sanity-check against
`given/consumer.yaml`'s `PROCESS_MS=500` (roughly 2 items/s per replica).
Pick something small enough that a real backlog actually triggers a
scale-up within this task's bounded wait, and large enough that the
baseline producer rate (~2 items/s, matched 1:1 by one consumer replica)
doesn't constantly hover right at the edge and flap.

Also worth deciding deliberately rather than leaving on the default:
`behavior.scaleDown.stabilizationWindowSeconds`. The HPA default is
**300 seconds** -- a real, defensible production value (it exists
specifically to stop a momentarily-empty queue from causing a scale-down
that then immediately has to scale back up). But it also means: if you
leave it unset, the validator's scale-down assertion has to wait up to
five minutes after the queue empties before it can even start seeing
replicas drop. Setting it to something like `60` is just as legitimate a
choice for this exercise and makes your own iteration loop much faster.
