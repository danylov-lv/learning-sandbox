# 09 — RMQ vs Kafka writeup

## Backstory

You've built and operated a production Scrapy scraper farm for years, with
competing spider processes consuming work from RabbitMQ queues and publishing
scraped price updates back into RMQ for downstream consumers. It's been solid
infrastructure: simple routing via exchanges, competing consumers sharing work,
dead-letter exchanges for poison messages, quick ack/nack logic. Recently,
three requests landed in the same month:

- The analytics team wants to spin up an independent copy of the price stream
  without stealing messages from anyone else (two consumers of the same data
  at different speeds).
- The pricing team needs to replay last Tuesday's scraped prices through a
  newly-trained ML model without re-scraping (replay from a fixed point in
  the stream).
- Your ops team is considering splitting the ingestion pipeline into
  finer-grained consumers per category, each tracking its own progress
  independently, and they're curious whether managing N independent consumer
  groups is easier than careful queue topology.

You've now seen Kafka (via tasks 01–08 of this module). Someone asks: "Do we
need to migrate to Kafka? Where would it actually help us? Where would it be
overkill?" Write down an honest engineering analysis grounded in what you've
learned from building with both.

## What's given

- This module's entire task suite (01–08), which has taught you:
  - How Kafka's log-and-offset model differs from RMQ's queue-and-ack model.
  - Consumer groups and partition assignment.
  - Offset commits and manual replay.
  - Idempotent consumers and exactly-once semantics.
  - Event-time windowing.
  - Consumer lag monitoring.
  - Log compaction and latest-state topics.
  - Transactional exactly-once across topics.
- A structured template (`ANSWER.md`) with five required section headings and
  guiding questions under each — no answers filled in.
- `NOTES.md` for your post-task reflection.

## What's required

1. Fill in every section of `ANSWER.md` with real substance, grounded in what
   you've learned from tasks 01–08 and the concepts in those tasks:
   - `## The current RMQ pipeline` — describe the scraper setup you're
     evaluating (producers, queues, competing consumers, ack model).
   - `## Where Kafka would help` — map each pain point to a concrete Kafka
     capability (replay, consumer groups, ordering, log compaction, lag
     monitoring, retention as a buffer).
   - `## Where Kafka would NOT help / would be overkill` — list RMQ's genuine
     strengths (per-message routing, priority queues, competing-consumer load
     balancing, low operational overhead).
   - `## The partition-count / ordering tradeoff` — explain the tension between
     Kafka's per-partition ordering guarantee and parallelism constraints vs
     RMQ's unbounded competing-consumer parallelism.
   - `## Migration verdict` — what you'd actually move to Kafka, what you'd
     keep in RMQ, and the one-sentence decision rule you'd tell a teammate.

2. Fill in `NOTES.md` with your reflection: what surprised you most about the
   differences, any gotchas you hit while learning, and open questions that
   would drive a real migration decision.

## Completion criteria

From this task's directory:

```
uv run python tests/validate.py
```

The validator checks:
- `ANSWER.md` exists and contains all five required `## ` section headings
  (exact match).
- Each section is substantially filled with your own prose (at least ~250
  characters beyond the shipped guiding prompt).
- The writeup mentions a required set of concept keywords at least once:
  `replay`, `compaction`, `consumer group`, `offset`, `exactly-once` (or
  `idempoten`), `backpressure` (or `lag`), `partition`, `retention`. Missing
  keywords → NOT PASSED with a list.
- `NOTES.md` is filled beyond the template headers (at least ~300 characters).
- On success: `PASSED`.

## Estimated evenings

1

## Topics to read up on

- Log vs. queue: append-only retention, offset tracking, replay semantics
- Consumer groups and competing consumers: partition assignment, independence
- Offset commits: manual vs. automatic, at-most-once vs. at-least-once
- Exactly-once delivery: idempotency + offset-in-transaction
- Backpressure and consumer lag: monitoring and alerting
- Log compaction and latest-state topics
- Per-key ordering and partition semantics vs. unbounded parallelism
- Kafka transaction model (exactly-once topic-to-topic)
- Operational overhead: single-node broker vs. distributed Kafka cluster
