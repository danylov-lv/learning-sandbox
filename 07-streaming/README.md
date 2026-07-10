# 07 — Streaming

## Backstory

You've run RabbitMQ in production for years: exchanges, queues, competing
consumers, acks and requeues, DLXs. It works. Then a new requirement lands —
the pricing team wants to replay last Tuesday's price stream through a new
model, the analytics team wants their own independent read of the same events
without stealing them from anyone, and someone needs per-category price
aggregates in 15-minute windows that stay correct when a consumer crashes
mid-stream. None of that is what a queue is for. A queue deletes a message once
it's acked; there is no "read it again from the start", no two independent
readers of the same stream, no history.

This module is Kafka (running as redpanda) for someone who already thinks in
queues. The mental shift is log-vs-queue: an append-only, retained, replayable
log where consumers track their own **offset** instead of the broker tracking
acks. Everything else follows from that — consumer groups vs competing
consumers, offsets vs acks, retention and re-reads, exactly-once built on top of
at-least-once, event-time windowing, lag monitoring, and compacted topics for
latest-state. The domain is the same scraped price stream from modules 04–06,
now arriving as a live event stream that consumers fold into Postgres.

## Stack / quickstart

Prerequisites: Docker with compose v2, uv.

```bash
cd 07-streaming
uv sync
docker compose up -d
```

This brings up:

- **redpanda** — a single-node, Kafka-API-compatible broker (no ZooKeeper, no
  JVM). Host clients connect at `localhost:19092`; in-container clients use
  `redpanda:9092`. Admin API on `19644`. Transactions and idempotence are on by
  default. Two listeners are configured so the same broker is reachable both
  from inside the compose network and from your host `uv run` scripts.
- **console** — Redpanda Console web UI at http://localhost:8307. Browse topics,
  partitions, consumer groups, lag, and messages — handy for watching what your
  consumers are doing.
- **warehouse** — Postgres 16 on host port `54307` (db `streaming`,
  user/password `sandbox`/`sandbox`), pre-seeded with schemas `core`, `ops`,
  `mart`. Consumers fold the stream into tables here.

Ports are overridable via `SANDBOX_07_PORT`, `SANDBOX_07_KAFKA_PORT`,
`SANDBOX_07_REDPANDA_ADMIN_PORT`, `SANDBOX_07_CONSOLE_PORT` — distinct from other
modules so several stacks can run at once.

**Connecting from the host.** Clients (`confluent-kafka`) reach the broker at
the bootstrap server `localhost:19092`. The shared helpers in
`harness/common.py` wrap this: `kafka_bootstrap()`, `admin_client()`,
`create_topic()`, `produce_events()`, `drain()`, `end_offsets()`,
`committed_offsets()`, `consumer_lag()`, plus the usual `pg_connect()`. Module
topics are named with the prefix `s07.`; `reset_topics()` clears them for a
clean slate.

**Data.** `uv run python generate.py` writes a deterministic (seed `70707`)
event stream to `data/events.ndjson` — `~200k` scraped price-update events over
a 2-hour event-time window, with ~2% late events (earlier `event_ts` than their
publish position) that make event-time windowing non-trivial. Everything under
`data/` is gitignored and disposable, except `data/ground-truth.json`, the
committed answer key validators check against.

## Tasks

| # | Task | Objective | Effort |
|---|------|-----------|--------|
| 01 | log-vs-queue-and-offsets | Publish the price stream; prove two consumer groups each read the full log independently and history re-reads from offset 0 (what RMQ can't do) | 1 evening |
| 02 | delivery-semantics | Manual offset commits: at-most-once vs at-least-once; survive an injected crash mid-stream with zero message loss | 1 evening |
| 03 | consumer-groups-rebalancing | Partition assignment across a consumer group; trigger a rebalance and observe reprocessing/reassignment consequences | 1 evening |
| 04 | exactly-once-into-postgres | At-least-once delivery + idempotent upsert / offset stored in the same Postgres txn = exactly-once aggregate despite redeliveries | 1-2 evenings |
| 05 | windowed-aggregation | Event-time tumbling windows (per-category price aggregates), correct late-event assignment | 1 evening |
| 06 | lag-monitoring | Compute consumer-group lag (high-watermark minus committed) and alert past a threshold under a produce burst | 1 evening |
| 07 | compacted-topics | Compacted topic for latest-state per product; materialize a current-price table that matches last-write-wins | 1 evening |
| 08 | kafka-transactions-eos | Transactional read-process-write between topics (transactional producer + read_committed) for topic-to-topic exactly-once | 1-2 evenings |
| 09 | rmq-vs-kafka-writeup | Written: which parts of a production RMQ pipeline benefit from Kafka, which don't, why | 1 evening |
| 10 | capstone-streaming-pipeline | Multi-evening: full price-stream → exactly-once aggregates + windows + lag monitoring in Postgres, consistent across consumer restarts/rebalances mid-stream. CP1 steady pipeline, CP2 chaos consistency, CP3 DESIGN.md | multi-evening |

`k8s-bonus` is optional and carries zero capstone weight — deploying a consumer
as a Deployment on a local cluster and watching a consumer-group rebalance when
pods scale; skip it freely, nothing else depends on it.

## Cross-module ties

- The domain is the **scraped price stream** shared with modules 04–06, but this
  module is fully self-contained: it generates its own corpus and stands up its
  own broker and warehouse. No other module's stack needs to be running.
- The throughline is the **RabbitMQ contrast**. Every task is framed against
  what a queue does and doesn't do: competing consumers vs consumer groups, acks
  vs offsets, requeue vs replay-from-offset, no-history vs retained log. Task 09
  makes that contrast explicit in writing.

## Topics to read up on

- The log abstraction: append-only partitions, offsets, retention, replay
- Consumer groups and partition assignment vs competing consumers on a queue
- Offset commits: auto vs manual, at-most-once vs at-least-once vs exactly-once
- Rebalancing protocols and the cost of reprocessing on reassignment
- Idempotent consumers: upsert + offset-in-the-same-transaction
- Event-time vs processing-time, tumbling windows, late-arrival handling
- Consumer lag: high watermark minus committed offset, and alerting on it
- Log compaction and latest-state (last-write-wins) topics
- Kafka transactions and `read_committed` for topic-to-topic exactly-once

## How to work

Per-task `README.md` holds the backstory and completion criteria; `src/` has the
scaffolds you fill in; `tests/validate.py` grades it against
`data/ground-truth.json` and the live broker/warehouse; `NOTES.md` is your
post-task writeup. `.authoring/` contains spoilers — don't read it before
finishing a task.
