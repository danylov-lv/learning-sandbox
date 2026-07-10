# Module 07 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the exact
distributions, the event-stream contract, and the ground-truth semantics that
the tasks and validators depend on. Read it afterwards if you want to see how
the corpus was built.

This file is the shared contract for every agent working on this module
(generator, docker/infra, consumers, validators). If you change a number here,
regenerate the corpus and update every consumer in the same change.

## Warehouse and broker

- Postgres, db `streaming`, user `sandbox`, password `sandbox`. Host port
  `54307`, env override `SANDBOX_07_PORT`. Schemas: `core`, `ops`, `mart`
  (`ops` for run/audit metadata — offsets, watermarks, lag snapshots; `core`
  and `mart` for aggregates). Tasks create their own tables.
- Redpanda (Kafka API). Host clients connect at `localhost:19092`
  (env `SANDBOX_07_KAFKA_PORT`); in-container clients use `redpanda:9092`. Two
  listeners are configured: internal `PLAINTEXT://redpanda:9092` and external
  `OUTSIDE://localhost:${SANDBOX_07_KAFKA_PORT}`. Admin API on `19644`
  (`SANDBOX_07_REDPANDA_ADMIN_PORT`). Redpanda Console UI on `8307`
  (`SANDBOX_07_CONSOLE_PORT`). Transactions and idempotence are on by default
  (redpanda enables them; we do not disable). All added to root `CONVENTIONS.md`.
- Topic naming convention: every module topic starts with the prefix `s07.`.
  `harness/common.py:reset_topics("s07.")` deletes them all for a clean slate.

## The corpus (deterministic, seed 70707)

A single stream of scraped price-update events. One
`np.random.default_rng(70707)` stream drives everything; `SCALE` (env, default
`1.0`) only scales the event count. Written to `data/events.ndjson`, one JSON
object per line, in publish/seq order (gitignored). The answer key is
`data/ground-truth.json` (committed).

### Universe

- `N_PRODUCTS = 5000`, ids `1..5000`.
- 8 categories in fixed Zipf-rank order, selection weight `w_rank ∝ 1/rank^1.1`
  (rank 0..7, most to least popular): `electronics`, `home-goods`, `kitchen`,
  `toys`, `sporting-goods`, `office-supplies`, `beauty`, `apparel`. Every
  product is assigned exactly one category at universe-build time, drawn with
  these weights (so category sizes are themselves skewed). A product's category
  never changes; each event's `category` is that of its `product_id`.
- 6 source domains (`.example` TLD), chosen uniformly per event (no skew):
  `shopnest.example`, `dealbarn.example`, `cartify.example`,
  `brightbuy.example`, `thriftloop.example`, `primemart.example`.
- Per-category price profile, lognormal `price = exp(normal(ln(median), sigma))`,
  independent draw per event (each event is a fresh scrape of a possibly-changed
  price), rounded to 2 decimals:

  | category | median | sigma |
  |---|---|---|
  | electronics | 120 | 0.9 |
  | home-goods | 45 | 0.7 |
  | kitchen | 35 | 0.6 |
  | toys | 25 | 0.6 |
  | sporting-goods | 55 | 0.7 |
  | office-supplies | 15 | 0.5 |
  | beauty | 20 | 0.5 |
  | apparel | 30 | 0.6 |

- Currency weights `USD 0.60`, `EUR 0.25`, `GBP 0.15`, drawn independently per
  event.
- `in_stock`: Bernoulli, `P(true) = 0.85`, independent per event.

### Stream

- Event-time window: `2025-07-01T00:00:00Z` to `2025-07-01T02:00:00Z` (2 hours).
- Total events `E = round(200000 * SCALE)`.
- Events are generated in NON-DECREASING event-time order: `E` uniform
  millisecond offsets in `[0, 7_200_000)` are drawn and sorted ascending; the
  sorted order defines the stream. Timestamps have millisecond precision,
  format `2025-07-01T00:37:12.123Z`.
- `event_id == seq == 0..E-1` in that time order (globally unique, monotonic).
  All other per-event arrays are indexed by seq, so array index `i` is the
  `i`-th event in the stream.
- Product selection per event: Zipf popularity within the universe. Each product
  id gets a random rank via `rng.permutation(N_PRODUCTS)+1`, weight
  `1/rank^1.2`, renormalized over all products; events draw product ids with
  that weight. Some products update far more often than others (this is what
  makes log compaction and latest-state interesting).

### Late events (the event-time twist)

- `late_count = round(E * 0.02)` events (~2%) are "late". After the ascending
  corpus is built, `late_count` events are selected uniformly (without
  replacement) and their `event_ts` is REDUCED by a random whole number of
  minutes in `[1, 15]` (clamped so it never falls below the window start
  `00:00:00.000`). Their POSITION in the file (publish order, = seq) is
  unchanged; only `event_ts` moves earlier.
- Consequence, and the pedagogical point: publish order (seq / Kafka offset) is
  strictly monotonic, but `event_ts` is NOT strictly monotonic — a late event
  sits at a later seq than events with a larger `event_ts`. Event-time window
  assignment (task 05) must therefore use `event_ts`, not arrival/offset order.
  Because late events only move earlier and clamp at the window start, every
  event's `event_ts` still lands inside `[00:00:00, 02:00:00)`, so the 8
  tumbling windows partition all `E` events exactly.

### Draw order (fixed — do not reorder without regenerating)

1. Universe: category assignment (`choice`), popularity permutation.
2. Stream: timestamps (`integers` then sort), product ids (`choice`),
   source ids (`integers`), currency ids (`choice`), `in_stock` (`random`),
   prices (per-category `lognormal`, category order), late-event selection
   (`choice`) and reduction minutes (`integers`).

### Event record shape

One JSON object per line in `events.ndjson`, in seq order:

```json
{"event_id": 0, "seq": 0, "product_id": 4213, "category": "kitchen", "source_site": "cartify.example", "price": 34.99, "currency": "USD", "in_stock": true, "event_ts": "2025-07-01T00:00:00.041Z"}
```

## `data/ground-truth.json` (committed answer key)

Computed by the generator while it plants the corpus. Top-level shape:

```json
{
  "seed": 70707,
  "scale": 1.0,
  "event_window": {"start": "2025-07-01T00:00:00Z", "end": "2025-07-01T02:00:00Z"},
  "total_events": <E>,
  "late_events": <late_count>,
  "n_products": 5000,
  "distinct_products_with_events": <int>,
  "recommended_partitions": 6,
  "constants": {
    "categories": [...8...],
    "sources": [...6...],
    "currency_weights": {"USD": 0.6, "EUR": 0.25, "GBP": 0.15}
  },
  "price_sum_all": <float, sum of price over ALL events, 2 decimals>,
  "per_category_totals": {"electronics": {"count": int, "price_sum": float}, ... all 8 ...},
  "windows": [{"start": "2025-07-01T00:00:00Z", "end": "2025-07-01T00:15:00Z"}, ... 8 ...],
  "window_category_agg": {
    "2025-07-01T00:00:00Z": {"electronics": {"count": int, "price_sum": float}, ...only categories present...},
    ... one entry per window START ...
  },
  "latest_state": {
    "count": <distinct products with >=1 event>,
    "price_sum": <float, sum over products of the price of that product's LAST event by seq, 2 decimals>,
    "sample": {"<product_id>": {"price": float, "currency": "USD", "in_stock": bool, "event_ts": "...", "seq": int}, ... 20 products ...}
  }
}
```

Field notes:

- `window_category_agg` uses EVENT_TIME (after late adjustment) to assign each
  event to a 15-minute tumbling window (`floor((event_ts - start) / 15min)`).
  This is the correct answer key for task 05 (windowed aggregation).
- `latest_state` uses LAST-WRITE-WINS by PUBLISH ORDER (seq), NOT event-time.
  This matches Kafka log-compaction semantics: compaction keeps the last
  *written* value per key. A late event with an earlier `event_ts` but later
  seq still wins its product's latest state. This deliberate distinction
  (compaction = publish-order, windowing = event-time) is the pedagogical point
  separating task 05 from task 07. This is the answer key for task 07.
- `latest_state.sample` holds the 20 most-frequently-updated products (ties
  broken by ascending product id) with their last-write-wins state, for cheap
  spot-checks.
- All price sums are rounded to 2 decimals. Validators should compare price sums
  with a tolerance of `0.05` to stay safe against float summation order.
- Consistency invariants validators can assert directly:
  - lines in `events.ndjson` == `total_events`.
  - sum of all `window_category_agg` counts == `total_events`.
  - sum of `per_category_totals` counts == `total_events`.
  - recomputing `latest_state.price_sum` (last event per product in file order)
    matches within `0.05`; likewise `price_sum_all`.

## Task plan

| # | dir | focus |
|---|-----|-------|
| 01 | log-vs-queue-and-offsets | publish the stream; two consumer groups each read the full log independently; history re-read from offset 0 |
| 02 | delivery-semantics | manual offset commits; at-most-once vs at-least-once; survive an injected mid-stream crash with zero loss |
| 03 | consumer-groups-rebalancing | partition assignment across a group; trigger a rebalance; observe reprocessing/reassignment |
| 04 | exactly-once-into-postgres | at-least-once delivery + idempotent upsert / offset in the same Postgres txn = exactly-once aggregate |
| 05 | windowed-aggregation | event-time tumbling windows (per-category), correct late-event assignment |
| 06 | lag-monitoring | consumer-group lag (high-watermark minus committed), alert past a threshold under a produce burst |
| 07 | compacted-topics | compacted topic for latest-state per product; materialize a current-price table matching last-write-wins |
| 08 | kafka-transactions-eos | transactional read-process-write between topics (transactional producer + read_committed) |
| 09 | rmq-vs-kafka-writeup | written analysis: which parts of a production RMQ pipeline benefit from Kafka, which don't |
| 10 | capstone-streaming-pipeline | full pipeline: exactly-once aggregates + windows + lag monitoring, consistent across restarts/rebalances |

`k8s-bonus` is optional and carries zero capstone weight.

## Ports table addition

Added to root `CONVENTIONS.md`:

| Module | Service | Host port | Env var |
|---|---|---|---|
| 07-streaming | Postgres | 54307 | `SANDBOX_07_PORT` |
| 07-streaming | Redpanda (Kafka API) | 19092 | `SANDBOX_07_KAFKA_PORT` |
| 07-streaming | Redpanda (Admin API) | 19644 | `SANDBOX_07_REDPANDA_ADMIN_PORT` |
| 07-streaming | Redpanda Console | 8307 | `SANDBOX_07_CONSOLE_PORT` |
