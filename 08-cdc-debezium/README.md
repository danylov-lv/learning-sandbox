# 08 — CDC with Debezium

## Backstory

You scrape prices for a living: poll a page, diff it against what you saw
last time, emit a change if something moved. It works, but it costs a
request every poll whether or not anything changed, and you're always at
least one interval behind reality.

Now flip the problem around. Imagine you *owned* the marketplace database
instead of scraping it from outside — a `shop.offers` table that sellers
update directly: price changes, restocks, delistings. You wouldn't poll your
own database on an interval and diff snapshots; you'd read the database's own
write-ahead log and get told about every change the instant it commits, with
zero missed intervals and zero wasted polls. That's Change Data Capture:
change-detection seen from the database side instead of the scraper side.
Debezium is a Kafka Connect plugin that turns Postgres's logical replication
stream into a Kafka topic per table, one JSON event per insert/update/delete.

This module builds that pipeline end to end — source Postgres → Debezium →
Kafka (redpanda) → a downstream mart — and works through the operational
reality of running it: the snapshot-then-stream lifecycle, decoding change
events, handling updates and deletes downstream, schema evolution without
breaking consumers, measuring replica lag, and materializing exactly-once
into a mart that must provably converge with the source.

## Stack / quickstart

Prerequisites: Docker with compose v2, uv.

```bash
cd 08-cdc-debezium
uv sync
docker compose up -d
uv run python generate.py
```

This brings up:

- **source** — Postgres 16 on host port `54308` (db `shop`, user/password
  `sandbox`/`sandbox`), the CDC-captured OLTP database. Started with
  `wal_level=logical` so Debezium can read its write-ahead log via logical
  replication. Schema `shop`: `products` (mostly-static dimension) and
  `offers` (the hot table — sellers' price/stock changes hit this one).
  `generate.py` seeds it deterministically; this initial state is exactly
  what a connector's snapshot phase captures.
- **mart** — Postgres 16 on host port `54318` (db `mart`, user/password
  `sandbox`/`sandbox`), pre-seeded with empty schemas `replica`, `ops`,
  `mart`. Tasks build their own tables here and fold the change stream in.
- **redpanda** — Kafka-API-compatible broker. Host clients connect at
  `localhost:19093`; in-container clients use `redpanda:9092`. Admin API on
  `19645`. Same dual-listener setup as module 07.
- **connect** — Kafka Connect running the Debezium Postgres connector
  (`debezium/connect:3.0.0.Final`). REST API on host port `8383`. Each task
  registers its own connector via this REST API (see
  `harness/common.py:register_connector()` / `wait_for_connector_running()`);
  nothing is pre-registered by the stack itself.
- **console** — Redpanda Console at http://localhost:8308, to browse topics
  and watch change events land.

Ports are overridable via `SANDBOX_08_SOURCE_PORT`, `SANDBOX_08_MART_PORT`,
`SANDBOX_08_KAFKA_PORT`, `SANDBOX_08_REDPANDA_ADMIN_PORT`,
`SANDBOX_08_CONSOLE_PORT`, `SANDBOX_08_CONNECT_PORT`.

**Registering a connector.** Tasks PUT a connector config to
`http://localhost:8383/connectors/<name>/config`. `harness/common.py`
provides `debezium_pg_connector_config()` (a correct baseline config, for
validators — some tasks ask you to write your own from scratch),
`register_connector()`, `wait_for_connector_running()`, `connector_status()`,
and `delete_connector()`. Every connector's `slot.name` / `publication.name`
/ `topic.prefix` must be unique per task (convention: connector `s08-tNN`,
slot `s08_tNN_slot`, publication `s08_tNN_pub`, topics
`s08.tNN.shop.<table>`) — see `.authoring/design.md`.

**Decoding change events.** The Connect worker uses `JsonConverter` with
schemas enabled (`{"schema": ..., "payload": ...}` envelopes) — set
explicitly in `docker-compose.yml`. `harness/common.py:decode_value(raw)`
unwraps the envelope (and handles schemas-disabled and tombstone records
too); `change_op(payload)` returns `(op, before, after)` with
`op in {'c','u','d','r'}`. `shop.offers` and `shop.products` have
`REPLICA IDENTITY FULL`, so `before` is the full pre-image on updates and
deletes, not just the primary key.

**Data.** `uv run python generate.py` seeds `shop.products` (~5000 rows) and
`shop.offers` (~20000 rows) directly into the source database via `COPY` —
Zipf category popularity, log-normal prices per category, weighted
currencies, ~85% in stock. Deterministic, seed `80808`, respects `SCALE`.
Also writes `data/ground-truth.json` (committed), the snapshot task's answer
key: row counts, price sum, per-category offer counts. `generate.py` also
exports `build_workload(seed, n_insert, n_update, n_delete)`, a deterministic
insert/update/delete burst builder later tasks' validators reuse to drive
reproducible change bursts against the source.

## Tasks

| # | Task | Objective | Effort |
|---|------|-----------|--------|
| 01 | connector-setup-snapshot-vs-streaming | Register a Debezium connector; observe the snapshot phase (`op=r` per existing row) hand off to streaming (`op=c/u/d`) | 1 evening |
| 02 | change-event-anatomy | Decode the full envelope: schema vs payload, `source` block, LSN/`ts_ms`, and the decimal-as-base64 encoding of `NUMERIC` columns | 1 evening |
| 03 | updates-and-deletes-downstream | Apply `before`/`after` diffs and tombstones to a downstream replica table correctly, including deletes | 1 evening |
| 04 | schema-evolution | Add/rename a column on the source table without breaking a running connector or consumer | 1-2 evenings |
| 05 | replica-lag-and-alerting | Measure replication slot lag (bytes and time) and alert past a threshold under a change burst | 1 evening |
| 06 | exactly-once-materialization | LSN-ordered idempotent upsert into the mart so redelivery/restart doesn't corrupt state (ties to module 07 task 04) | 1-2 evenings |
| 07 | cdc-vs-rescraping-writeup | Written: where CDC beats periodic re-scraping/re-querying, where it's overkill | 1 evening |
| 08 | capstone-converge | Multi-evening: full source→Debezium→mart pipeline that provably converges (`mart == source`) after a scripted insert/update/delete burst, survives connector restarts | multi-evening |

## Cross-module ties

- Shares the **redpanda + confluent-kafka** patterns from module 07 —
  `harness/common.py` here mirrors 07's shape (topic helpers, `drain()`,
  lag helpers), just pointed at this module's own broker and a `s08.` topic
  prefix.
- Task 06 (exactly-once-materialization) is the direct continuation of
  module 07 task 04 (exactly-once-into-postgres): idempotent upsert +
  offset/LSN bookkeeping in the same transaction, this time driven by a
  change-data-capture stream instead of an application-level event stream.
- Task 08's convergence grading (`mart == source`) is a straightforward
  `SELECT` comparison run by the validator — no reference solution, just an
  independently-computed check against the live source.

## Topics to read up on

- Logical replication in Postgres: `wal_level=logical`, replication slots,
  publications, the `pgoutput` plugin
- Change data capture: snapshot phase vs streaming phase
- The Debezium change-event envelope: `before`/`after`/`source`/`op`/`ts_ms`
- `REPLICA IDENTITY` (`DEFAULT` vs `FULL`) and what it does to `before`
  images on UPDATE/DELETE
- Kafka Connect: workers, connectors, tasks, config/offset/status storage
  topics, the REST API
- Tombstone records and `tombstones.on.delete`
- Replication slot lag and the operational hazard of an orphaned slot
  pinning WAL
- Schema evolution strategies that don't break a running connector or its
  consumers
- Exactly-once materialization: idempotent upsert keyed by source LSN/offset

## How to work

Per-task `README.md` holds the backstory and completion criteria; `src/` has
the scaffolds you fill in; `tests/validate.py` grades it against
`data/ground-truth.json` and the live stack; `NOTES.md` is your post-task
writeup. `.authoring/` contains spoilers (exact connector configs, the
verified envelope shape, ground-truth internals) — don't read it before
finishing a task.
