# INCIDENT — SEV1 — 2026-03-11 — Scraping platform + Delivery API

Status: resolved. This document is the raw incident record assembled from
monitoring, logs, and chat during the event. It contains no root-cause
analysis and no remediation plan — those are the task. Read it as you
would read a real incident channel and dashboard export: some of what's
here matters, some of it is noise, and nobody in the room had the full
picture while it was happening.

Duration (first customer impact to confirmed all-clear): **4h05m**
(08:41–12:46).

Services involved: `scrape-worker` fleet (RabbitMQ consumers), `core-shared-pg`
(shared Postgres connection pool), `delivery-api` (customer-facing export/
webhook service — no scraping logic of its own).

---

## Timeline

**08:41** — Synthetic monitor for target `sunrise-outdoor.example` (one of
~40 sites polled by the `scrape.parse.default` queue) reports latency
degradation:

```
synthetic-monitor sunrise-outdoor.example
  p50: 340ms -> 1180ms
  p95: 610ms -> 4900ms
  status_code: 200 (unchanged)
```

No alert fired. The synthetic-monitor alert rule is `status_code NOT IN
(200..299)` — latency is not part of the rule.

**08:45** — Data-quality dashboard, field-extraction success rate for
`sunrise-outdoor.example` product-detail pages:

```
07:00  97.8%
08:00  97.6%
08:45  63.1%
09:00  61.4%  (holding)
```

No alert fired. This dashboard has no configured threshold — it's a
Grafana panel, view-only, not wired to Alertmanager.

**09:00** — PagerDuty pages on-call: `RabbitMQ queue depth
scrape.parse.default > 10000 (5m avg)`. This is the incident's formal
start.

**09:03** — Sampled worker log lines (three consecutive from the same
worker, ~30s apart):

```
09:03:11 worker-07 ERROR scrape.parse.default task=a83f2c1
  KeyError: 'sale_price' in parse_listing()
  elapsed=812ms (fetch=430ms, stage_upsert=340ms, parse=42ms)
  action=nack(requeue=True)

09:03:44 worker-07 ERROR scrape.parse.default task=a83f2c1
  KeyError: 'sale_price' in parse_listing()
  elapsed=798ms (fetch=411ms, stage_upsert=352ms, parse=35ms)
  action=nack(requeue=True)

09:04:15 worker-07 ERROR scrape.parse.default task=a83f2c1
  KeyError: 'sale_price' in parse_listing()
  elapsed=770ms (fetch=402ms, stage_upsert=336ms, parse=32ms)
  action=nack(requeue=True)
```

Same `task=a83f2c1` across all three lines.

**09:05** — Current retry policy for `scrape.parse.default`, as deployed
(`retry-policy.yaml`, last changed 2025-11-02, changelog: "add exponential
backoff to parse queue"):

```yaml
retry_policy:
  queue: scrape.parse.default
  max_attempts: 5
  requeue_immediate: true
  backoff:
    strategy: exponential
    base_ms: 0
    factor: 2
    max_ms: 30000
```

**09:07** — RabbitMQ queue depth reading, `scrape.parse.default`:

```
09:00  ~800
09:15  ~19,631
```

**09:12** — On-call chat (`#incidents`):

```
[09:12] priya: queue depth on scrape.parse.default is climbing fast,
        19.6k and rising. anyone touch a deploy?
[09:13] dmitri: nothing on my end. could be a traffic spike from the
        catalog refresh job?
[09:14] priya: catalog refresh doesn't touch this queue
[09:15] dmitri: consumer lag graph is ugly. scaling worker replicas,
        11 -> 20, autoscaler should've caught this already tbh
```

**09:35** — Autoscaler event log:

```
09:35:02 autoscaler: metric queue_depth{queue="scrape.parse.default"}
  = 44738, threshold=10000, sustained 5m -> scale
  deployment/scrape-worker replicas 11 -> 20
```

**09:40** — `delivery-api` p99 latency and error rate:

```
08:00-09:35  p99=210ms  5xx_rate=0.1%
09:40        p99=6100ms 5xx_rate=41%
09:55        p99=8900ms 5xx_rate=68%
```

**09:41** — Status page incident opened by support: "Some customers may
experience delayed or failing data export webhooks." First customer
tickets logged 09:44, 09:51, 09:58 (3 separate accounts, all referencing
webhook timeouts).

**09:52** — On-call chat:

```
[09:50] dmitri: replicas are at 20, queue depth still climbing??
[09:52] priya: also why is delivery-api throwing 503s. it doesn't even
        touch the scrape pipeline, does it?
[09:53] jae: checking now
[09:54] jae: delivery-api's pg pool is core-shared-pg. same as the
        scrape workers
[09:55] priya: huh. ok, unrelated for now, keep an eye on it
```

**09:58** — Postgres pool alert:

```
[ALERT] pgbouncer core-shared-pg: client_conns_waiting > 0 for 6m
  pool_size=22, in_use=27 (avg over 10m)
  firing since 09:52
```

**10:05** — Kubernetes restart counts, `deployment/scrape-worker`:

```
08:00-09:00   3 restarts
09:00-10:00  22 restarts
10:00-11:00  41 restarts (partial, in progress)
```

Sampled pod event: `Liveness probe failed: HTTP probe failed with
statuscode: 503` (readiness endpoint queries `core-shared-pg` for a
health-check row).

**10:10** — RabbitMQ queue depth: `~88,677`.

**10:22** — On-call chat:

```
[10:15] jae: pool_size on core-shared-pg is still 22. nobody's touched
        that config in months
[10:18] dmitri: workers are at 20 replicas x4 concurrency now, that's a
        lot of connections if they're all held at once
[10:20] priya: delivery-api on-call just paged separately, they're
        seeing full pool exhaustion from their side too
[10:22] dmitri: should we just scale workers down again?
[10:23] priya: if we scale down the queue backs up even faster, we're
        already not keeping up at 20
```

**10:40** — RabbitMQ queue depth: `~126,338`.

**10:58** — On-call chat:

```
[10:58] jae: sunrise-outdoor is still serving 200s but the HTML looks
        wrong when I curl it manually — half the DOM is missing
[10:59] priya: so every one of those is nacking and going right back on
        the queue
[11:00] dmitri: forever? nothing dead-letters this?
[11:01] jae: max_attempts is 5 per the policy file, then it should DLQ.
        checking whether that's actually happening
```

**11:10** — RabbitMQ queue depth: `164,000` (peak observed).

**11:11** — On-call chat:

```
[11:10] priya: we're not waiting on the DLQ math. pausing all consumers
        on scrape.parse.default and doing a manual purge-and-replay
        of the sunrise-outdoor backlog to a side queue
[11:11] dmitri: +1, doing it now
```

**11:11–11:22** — Consumers on `scrape.parse.default` paused; backlog
manually drained/redirected. `core-shared-pg` connection wait count drops
to 0 by 11:23.

**11:15** — `delivery-api` 5xx rate begins recovering: `68% -> 12%` over
the next 8 minutes as pool pressure releases.

**11:30** — `delivery-api` 5xx rate back under 1%. Status page updated:
"Fix implemented, monitoring."

**12:46** — Incident declared resolved. Queue depth on
`scrape.parse.default` back under 1,000; `core-shared-pg` connections
in-use steady at 9; no further worker restarts in the preceding 45
minutes.

---

## Evidence index (for reference)

- Synthetic monitor snapshot, `sunrise-outdoor.example`: 08:41.
- Data-quality dashboard export, field-extraction success rate: 08:45.
- Worker error log sample (3 lines, same task, retried in place): 09:03.
- `retry-policy.yaml` as deployed: 09:05.
- RabbitMQ queue depth readings: 09:00, 09:15, 09:35 (autoscaler
  snapshot), 10:10, 10:40, 11:10 (peak).
- Autoscaler event log: 09:35.
- `delivery-api` latency/error-rate readings: 09:40, 09:55, 11:15, 11:30.
- Status page + support ticket references: 09:41 onward.
- `pgbouncer` pool alert: 09:58.
- `deployment/scrape-worker` restart counts + sampled pod event: 10:05.
- On-call chat excerpts: 09:12, 09:52, 10:22, 10:58, 11:10.
