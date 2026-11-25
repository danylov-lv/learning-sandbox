# 07 — CDC vs re-scraping writeup

## Backstory

You've been running a distributed scraper farm for years. Your setup is proven: poll a marketplace page or API on a schedule, diff the response against what you cached last time, emit a change event if something moved. Simple, resilient, and cost-predictable — you know exactly how many requests per day you'll make.

Now you've built the other side of the equation in this module: Change Data Capture. Instead of polling from the outside, you're reading a database's own write-ahead log via Debezium, getting told about every insert/update/delete the instant it commits — no polling overhead, no missed intervals between checks, no stale deltas. You've seen the snapshot phase, decoded the change-event envelope, handled updates and deletes correctly, evolved schemas without breaking consumers, measured replication slot lag, and built idempotent materialization.

But CDC isn't free: it requires database access, WAL retention discipline, a dedicated Kafka Connect infrastructure, careful handling of replication slots, and schema governance. Periodic re-scraping is simpler to operate and often sufficient. Someone asks: "Now that you understand CDC, when would you actually switch from polling? Where does CDC win? And where is it overkill?" Write down an honest engineering analysis.

## What's given

- This module's task suite (01–06), which has taught you:
  - Debezium connector registration and the snapshot-then-streaming lifecycle.
  - Change-event anatomy: `before`/`after` diffs, tombstones, `REPLICA IDENTITY`.
  - Applying changes to a downstream replica correctly.
  - Schema evolution without breaking running connectors or consumers.
  - Replication slot lag measurement under change bursts.
  - Idempotent, exactly-once materialization keyed by LSN.
- A structured template (`ANSWER.md`) with five required section headings and guiding questions under each — no answers filled in.
- `NOTES.md` for your post-task reflection.

## What's required

1. Fill in every section of `ANSWER.md` with real substance, grounded in what you've learned from tasks 01–06 and your experience as a scraper operator:
   - `## The re-scraping / re-query baseline` — describe the polling approach you've relied on (frequency, cost, latency, what you miss).
   - `## Where CDC wins` — map concrete pain points in polling to CDC capabilities (low-latency propagation, no missed intermediate states, WAL as source of truth, delete capture, snapshot backfill).
   - `## Where CDC is overkill / the wrong tool` — list scenarios where polling is simpler or necessary (small/low-churn data, third-party sites you can only scrape, no database access, operational overhead not justified).
   - `## The operational cost of CDC` — explain the burdens: replication slots pinning WAL, Kafka Connect operations, schema evolution discipline, snapshot cost on large tables.
   - `## Verdict` — write the decision rule: when you'd reach for CDC vs polling on a given data source.

2. Fill in `NOTES.md` with your reflection: what surprised you most about CDC vs polling, gotchas you hit, and open questions that would shape a real adoption decision.

## Completion criteria

From this task's directory:

```
uv run python tests/validate.py
```

The validator checks:
- `ANSWER.md` exists and contains all five required `## ` section headings (exact match).
- Each section is substantially filled with your own prose (at least ~200 characters beyond the shipped guiding prompt).
- The writeup mentions required concept keywords at least once: `replication slot` or `WAL`, `snapshot`, `latency` (or `freshness`/`staleness`), `backfill`, `schema evolution`, `tombstone` (or `delete` capture), `idempotent` (or `exactly-once`), `overkill` (or `re-scrape`/`polling`). Missing keywords → NOT PASSED with a list.
- `NOTES.md` is filled beyond the template headers (at least ~300 characters).
- On success: `PASSED`.

## Estimated evenings

1

## Topics to read up on

- Log-based CDC vs periodic polling: freshness, latency, and operational cost tradeoffs
- Replication slots and WAL retention: the cost of keeping change history
- Snapshot phase and backfill semantics: catching up a new consumer to current state
- Change-detection strategies in scraping vs CDC
- Schema evolution strategies that don't break a CDC pipeline
- Idempotent consumer logic and exactly-once semantics
- When to use CDC vs simpler polling approaches
