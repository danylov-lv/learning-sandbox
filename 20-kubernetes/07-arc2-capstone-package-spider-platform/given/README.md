# What's in `given/`

Someone on the team hand-wrote these four manifests to get the "spider
platform" running once, by hand, in a scratch namespace. They work -- but
every number is hardcoded, nothing is toggleable, there is no dev/prod
split, and the queue hostname is typed in as the literal string `redis`
because that's what they happened to name the Service that day. This is
the "before" picture. Your job in `chart/` is the "after": the same four
components, expressed as one proper Helm chart where every one of those
hardcoded choices becomes a value with a sane default.

Do not `helm template`/apply these directly as part of your chart -- they
are read-only reference material showing the shape of what each component
needs, not a scaffold to copy-paste into `templates/`. Copying the
structure is expected (a Deployment is a Deployment); copying the literal
hardcoded values defeats the point of the task.

## The four components

- **`target`** (`target-deployment.yaml` / `target-service.yaml`) --
  `sandbox20-app:1.0` in `server` mode. Stands in for the hostile site this
  platform would scrape. Nothing else in this fixture actually calls it
  over HTTP -- it exists so the chart has a fourth toggleable component and
  so a learner's `values.yaml` design has to account for a component that
  is pure server/Service, no queue wiring at all.
- **`queue`** (`queue-deployment.yaml` / `queue-service.yaml`) --
  `redis:7-alpine`, the actual work queue `producer` and `workers` share.
- **`producer`** (`producer-deployment.yaml`) -- `sandbox20-app:1.0` with
  `WORK_MODE=producer`, pushing synthetic scrape "URLs" onto the queue at
  `RATE_PER_S` items/second.
- **`workers`** (`workers-deployment.yaml`) -- `sandbox20-app:1.0` with
  `WORK_MODE=consumer`, draining the queue at one item per `PROCESS_MS`
  milliseconds per replica.

## What's hardcoded here that your chart must not hardcode

- `queue-service.yaml`'s name is the literal string `redis`, and both
  `producer-deployment.yaml` and `workers-deployment.yaml` set
  `REDIS_HOST` to that same literal string. In your chart, both
  containers must get `REDIS_HOST` from the queue Service's own rendered
  name (however you name it) -- never a literal `"redis"` typed twice in
  two different templates and hoping they stay in sync.
- `workers-deployment.yaml` has one replica, no `resources`, and probes
  with fixed numbers. Your chart must make replicas, resources, and every
  probe field (`initialDelaySeconds`, `periodSeconds`, `timeoutSeconds`,
  `failureThreshold`, not just the boolean "probe exists") values-driven.
- `producer-deployment.yaml`'s `RATE_PER_S` and `workers-deployment.yaml`'s
  `PROCESS_MS` are plain literals. Your chart renders both from values.
- Nothing here is toggleable -- delete `target-deployment.yaml` by hand
  and you also have to remember `target-service.yaml`. Your chart's
  `target.enabled` / `producer.enabled` flags do that in one flip.
- There's no dev/prod split -- this is the only version that exists. Your
  chart ships `values-dev.yaml` (cheap, one worker) and `values-prod.yaml`
  (three workers, real resources, a faster producer) on top of one shared
  `values.yaml` default.

## Rate contract worth internalizing before you write `values-dev.yaml`

A consumer replica's max throughput is deterministic: `1000 / PROCESS_MS`
items/second (it's a simulated sleep, not CPU work, so it does not depend
on the machine). For the pipeline to actually drain instead of backing up
forever, `producer.ratePerS` must stay below `workers.replicas * (1000 /
workers.processMs)` with real headroom. This repo's own dev/prod values
are calibrated this way on purpose -- worth checking the arithmetic
yourself before you pick numbers, rather than copying these.
