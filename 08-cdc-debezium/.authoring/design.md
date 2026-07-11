# Module 08 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
exact source schema, seed distributions, ground-truth semantics, topic/slot
naming, the verified Debezium connector config, and the envelope shape every
task and validator depends on. Read it afterwards if you want to see how the
module was built.

This file is the shared contract for every agent working on this module
(infra, generator, consumers, validators). If you change something here,
regenerate/reverify and update every consumer in the same change.

## Stack

- **source** Postgres 16, db `shop`, user/password `sandbox`/`sandbox`. Host
  port `54308`, env override `SANDBOX_08_SOURCE_PORT`. Started with
  `-c wal_level=logical -c max_wal_senders=10 -c max_replication_slots=10`
  (set via the `command:` array in docker-compose.yml, not
  `postgresql.conf`, so it survives without a custom image).
- **mart** Postgres 16, db `mart`, user/password `sandbox`/`sandbox`. Host
  port `54318`, env override `SANDBOX_08_MART_PORT`. Schemas `replica`,
  `ops`, `mart` pre-created, no tables — tasks create their own.
- **redpanda** v24.3.5 (same version as module 07). Host clients at
  `localhost:19093` (`SANDBOX_08_KAFKA_PORT`), in-container at
  `redpanda:9092`. Admin API `19645` (`SANDBOX_08_REDPANDA_ADMIN_PORT`).
  Console at `8308` (`SANDBOX_08_CONSOLE_PORT`).
- **connect** `debezium/connect:3.0.0.Final`. This exact tag was verified
  live — `debezium/connect:2.7` (no such tag), `2.7.3.Final`, `2.6`, and
  `3.0.0.Final` all exist on Docker Hub as of generation time; `3.0.0.Final`
  was picked as current-stable. REST API on host `8383`
  (`SANDBOX_08_CONNECT_PORT`), container port fixed at `8083`.
  `depends_on` redpanda/source/mart all healthy.

  Worker-level env (`docker-compose.yml`):
  ```
  BOOTSTRAP_SERVERS=redpanda:9092
  GROUP_ID=s08-connect
  CONFIG_STORAGE_TOPIC=s08-connect-configs
  OFFSET_STORAGE_TOPIC=s08-connect-offsets
  STATUS_STORAGE_TOPIC=s08-connect-statuses
  KEY_CONVERTER=org.apache.kafka.connect.json.JsonConverter
  VALUE_CONVERTER=org.apache.kafka.connect.json.JsonConverter
  KEY_CONVERTER_SCHEMAS_ENABLE=true
  VALUE_CONVERTER_SCHEMAS_ENABLE=true
  ```
  Note the worker's own bookkeeping topics use dashes
  (`s08-connect-configs`, not `s08.connect...`), deliberately outside the
  `s08.` dot-prefix used for data topics, so `reset_topics("s08.")` never
  touches Connect's own state.

  **Converter decision: JsonConverter with schemas ENABLED.** Every record
  value is `{"schema": {...}, "payload": {...}}`. This is heavier on the
  wire than schemas-disabled or Avro+registry, but it's self-describing (no
  external schema registry needed) and keeps the module dependency-free.
  Consumers must unwrap `payload` — `harness/common.py:decode_value()` does
  this and also tolerates schemas-disabled (bare dict) and tombstones (`None`
  value) so it works regardless of what an individual task's own connector
  config sets.

- **console** `redpandadata/console:v2.8.5` (same as module 07), port 8308.

## Source schema (`docker/source-init.sql`)

```sql
CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.products (
    product_id BIGINT PRIMARY KEY,
    title      TEXT NOT NULL,
    category   TEXT NOT NULL,
    brand      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shop.offers (
    offer_id   BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES shop.products(product_id),
    seller     TEXT NOT NULL,
    price      NUMERIC(12, 2) NOT NULL,
    currency   TEXT NOT NULL,
    in_stock   BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE shop.products REPLICA IDENTITY FULL;
ALTER TABLE shop.offers REPLICA IDENTITY FULL;
```

**REPLICA IDENTITY FULL, why:** Postgres's default replica identity
(`DEFAULT`) only logs the primary key in the WAL for UPDATE/DELETE, so a
Debezium `before` image would contain just `{"offer_id": N}` and nulls
elsewhere. `FULL` logs the entire old row, giving consumers a real `before`
image — needed so task 03 can diff `before` vs `after` to see which columns
actually changed, and so a delete's `before` carries enough context to
matter pedagogically (not just "row N is gone", but "row N, which looked
like this, is gone"). Verified live: an UPDATE on `shop.offers` produced a
`before` with every column populated (old price, old in_stock, etc.), not
just the PK. Trade-off, worth calling out to learners in task 02: `FULL`
means Postgres writes the whole old row to WAL on every UPDATE/DELETE, which
is heavier than `DEFAULT` on a high-churn table — a real production
decision, not a free lunch.

No publication or replication slot is created in `source-init.sql` — each
task's own connector creates its own (see naming convention below).

## Mart schema (`docker/mart-init.sql`)

```sql
CREATE SCHEMA IF NOT EXISTS replica;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS mart;
```

No tables. `replica` for a raw change-applied mirror, `ops` for run/offset
bookkeeping, `mart` for any derived aggregate a task wants — same three-way
split as module 07's warehouse.

## Topic / connector / slot / publication naming (per-task convention)

Every task's Debezium connector must use a name unique to that task so
concurrent or leftover state from one task never collides with another:

- connector name: `s08-tNN` (e.g. `s08-t01`)
- slot name: `s08_tNN_slot` (Postgres identifiers can't contain dots/hyphens
  cleanly in all contexts, hence underscores here)
- publication name: `s08_tNN_pub`
- `topic.prefix`: `s08.tNN` → Debezium publishes to
  `s08.tNN.shop.offers` and `s08.tNN.shop.products`

The throwaway probe connector used to verify this infra live (see below)
used `s08-probe` / `s08_probe_slot` / `s08_probe_pub` / `s08.probe` and was
fully torn down afterward — nothing from it is left in the stack.

`harness/common.py:reset_topics(prefix="s08.")` deletes every topic whose
name starts with `s08.` (data topics only, by construction — Connect's own
bookkeeping topics use `s08-connect-*` with a dash, not a dot, so they're
never touched by this).

**Operational rule, critical:** always `delete_connector()` AND
`drop_slot()` AND `drop_publication()` together when tearing down a
connector. Deleting only the connector leaves its replication slot behind;
an orphaned slot with no active consumer still pins WAL on the source
(`pg_replication_slots.restart_lsn` stops advancing), so Postgres cannot
recycle old WAL segments and disk usage grows unbounded until the slot is
dropped. Verified live: after `delete_connector()`, the slot briefly reports
`active=true` for a few seconds (the Debezium task's replication connection
takes a moment to actually close) — `drop_slot()` will raise
`ObjectInUse` (`psycopg.errors.ObjectInUse`) if called in that window.
Validators/tasks that automate teardown should poll `active=false` (via
`replication_slots()`) before calling `drop_slot()`, or retry once after a
short delay.

## The seeded corpus (deterministic, seed 80808)

`generate.py`, one `np.random.default_rng(80808)` stream. `SCALE` (env,
default `1.0`) scales both `n_products = round(5000 * SCALE)` and
`n_offers = round(20000 * SCALE)`. Seeds the SOURCE database directly via
`COPY` (not a file) — this initial state is exactly what a connector's
snapshot phase (`op=r`) captures, which is why there's no `data/events.*`
file the way module 07 has one.

### Universe (draw order)

1. Category assignment: `rng.choice(len(CATEGORIES), size=n_products, p=cat_w)`
   where `cat_w` is Zipf over rank (`w_rank ∝ 1/rank^1.1`), same 8 categories
   and same Zipf exponent as module 07 for consistency across the
   "marketplace" domain: `electronics, home-goods, kitchen, toys,
   sporting-goods, office-supplies, beauty, apparel` (most to least
   popular). A product's category never changes.
2. Popularity permutation: `rng.permutation(n_products) + 1`, weight
   `1/rank^1.2` (renormalized) — this drives which products get more offers
   below (Zipf-skewed, same exponent as module 07's per-product popularity).

### Products

- Brand: `rng.random(n_products) < 0.15` → `None` (15% unbranded); else
  uniform choice over 10 brand names (`BRANDS` in `generate.py`).
- Title: per-category loop (fixed `CATEGORIES` order) — for each category's
  product indices, draw an adjective index and a noun index
  (`rng.integers`), title = `f"{adjective} {noun}"`. Category-specific noun
  lists (`NOUNS` dict, 6 nouns per category) plus one shared 10-word
  `ADJECTIVES` list.

### Offers

1. `product_id` per offer: `rng.choice(1..n_products, size=n_offers,
   p=pop_weight)` — Zipf-skewed, so popular products accumulate more offers
   (multiple sellers).
2. `seller`: uniform `rng.integers` over 8 seller names (`SELLERS`).
3. `currency`: `rng.choice(["USD","EUR","GBP"], p=[0.60,0.25,0.15])`.
4. `in_stock`: `rng.random(n_offers) < 0.85`.
5. `price`: per-category loop (same `CATEGORIES` order), lognormal
   `exp(normal(ln(median), sigma))`, rounded to 2 decimals. Same
   `CATEGORY_PRICE_PROFILE` table as module 07 (median/sigma per category,
   e.g. electronics 120/0.9, office-supplies 15/0.5 — see `generate.py` for
   the full table).

Row counts at `SCALE=1.0`, verified live: `shop.products` = 5000,
`shop.offers` = 20000, `offers_price_sum` = 1884008.69,
`in_stock_count` = 17004.

### `data/ground-truth.json` (committed answer key)

```json
{
  "seed": 80808,
  "scale": 1.0,
  "n_products": 5000,
  "n_offers": 20000,
  "constants": {"categories": [...8...], "sellers": [...8...], "currency_weights": {"USD": 0.6, "EUR": 0.25, "GBP": 0.15}},
  "row_counts": {"products": 5000, "offers": 20000},
  "offers_price_sum": 1884008.69,
  "distinct_products_with_offers": <int>,
  "per_category_offer_counts": {"electronics": int, ... all 8 ...},
  "in_stock_count": 17004
}
```

This is the snapshot task's (01) answer key: after a fresh connector's
snapshot phase, `s08.tNN.shop.offers` must contain exactly
`row_counts.offers` `op=r` events, and summing their `after.price` (once
decoded past the Decimal encoding — see below) must match
`offers_price_sum` within a small tolerance. Convergence tasks (06, 08)
instead grade `mart == source` via a live `SELECT` comparison, not against
this file — the ground truth only describes the *initial* state, not any
post-burst state.

### `build_workload(seed, n_insert, n_update, n_delete)`

Pure function in `generate.py`, importable without a live stack (only
`numpy`). Builds — does not apply — a deterministic list of op dicts:

```python
{"op": "update", "table": "offers", "offer_id": int, "price": float, "in_stock": bool}
{"op": "delete", "table": "offers", "offer_id": int}
{"op": "insert", "table": "offers", "offer_id": int, "product_id": int,
 "seller": str, "price": float, "currency": str, "in_stock": bool}
```

Order in the returned list: all updates, then all deletes (drawn from the
remaining un-updated ids, so no offer is both updated and deleted in the
same call), then all inserts. Updates/deletes assume ids `1..n_offers`
already exist (i.e. `generate()` has run at a matching `SCALE`). Insert ids
start at `1_000_000 + (seed % 100_000) * 100` so different seeds don't
collide. Workload prices are drawn from a single generic
lognormal(median=40, sigma=0.8) distribution, deliberately NOT tied to the
product's real category profile — keeps the builder fully self-contained
(no dependency on `generate()`'s internal universe draw) at the cost of
category-price realism, which doesn't matter for a synthetic CDC-exercise
burst. Validators call this, then apply each op themselves via `psycopg`
against the source, then check the resulting Kafka events / mart state.

## Verified connector config (as actually run for the live probe)

Built by `harness/common.py:debezium_pg_connector_config()`:

```json
{
  "name": "s08-probe",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "plugin.name": "pgoutput",
    "database.hostname": "source",
    "database.port": "5432",
    "database.user": "sandbox",
    "database.password": "sandbox",
    "database.dbname": "shop",
    "topic.prefix": "s08.probe",
    "slot.name": "s08_probe_slot",
    "publication.name": "s08_probe_pub",
    "publication.autocreate.mode": "filtered",
    "table.include.list": "shop.offers,shop.products",
    "snapshot.mode": "initial",
    "tombstones.on.delete": "true"
  }
}
```

Registered via `PUT /connectors/s08-probe/config`, reached `RUNNING` (both
connector and its one task) within ~2 seconds of registration in the
verification run.

**Not set: `decimal.handling.mode`.** Left at the connector default
(`precise`). This means `NUMERIC` columns (`offers.price`) are NOT emitted
as JSON numbers — they arrive as the Kafka Connect `Decimal` logical type,
base64-encoded bytes of the unscaled value, e.g. `"price": "GSc="`. Verified
live: `base64.b64decode("GSc=") == b"\x19'"`, `int.from_bytes(...) == 6439`,
and `6439 / 10**2 == 64.39`, which matched the actual source row's price
exactly. This is intentionally left as the connector default rather than
"fixed" to `double` or `string` in the shared harness config, because
decoding it correctly is the specific point of task 02
(change-event-anatomy) — `harness/common.py:decode_value()` only unwraps the
JsonConverter envelope, it does NOT decode the price field for the learner.
A task's own consumer code must handle this (e.g. set
`decimal.handling.mode=double` or `=string` on its own connector, or decode
the base64 value manually using the field's `scale` from the JSON schema).

## Verified live proof (wave-1 infra check)

Run against a throwaway connector `s08-probe` (topic prefix `s08.probe`),
against the stock-seeded source (5000 products / 20000 offers):

- **Snapshot phase:** `s08.probe.shop.offers` received exactly 20000
  messages, all `op=r`, `before=None`, `after=<full row>` — one per existing
  source row, matching `shop.offers` row count exactly.
- **Streaming phase**, after one INSERT (`offer_id=999001`), one UPDATE
  (`offer_id=1`: price 64.39→88.88, in_stock true→false), one DELETE
  (`offer_id=2`) on the source:
  - `op=c` for the insert, `before=None`, `after=<new row>`.
  - `op=u` for the update, `before=<full old row, price 64.39/in_stock
    true>`, `after=<full new row, price 88.88/in_stock false>` — proves
    `REPLICA IDENTITY FULL` is producing a real before-image, not just the
    PK.
  - `op=d` for the delete, `before=<full row that was deleted>`,
    `after=None`, immediately followed by a **tombstone** record (message
    value `None`, key `{"offer_id": 2}`) — confirms
    `tombstones.on.delete=true` (the Debezium default) is in effect.
  - `decode_value()` / `change_op()` correctly handled all four shapes
    (`r`, `c`, `u`, `d`) plus the tombstone (`decode_value(None) is None`).

## Teardown verified

- `delete_connector("s08-probe")` → `True`, `list_connectors()` → `[]`.
- Slot briefly `active=true` right after connector deletion (task's
  replication connection hadn't closed yet); retried a few seconds later,
  `active=false`, then `drop_slot()` → `True`, `drop_publication()` → `True`,
  `pg_replication_slots` → empty. This active→inactive delay is the timing
  gotcha documented above.
- `reset_topics("s08.")` → deleted `s08.probe.shop.offers` and
  `s08.probe.shop.products`; Connect's own `s08-connect-*` bookkeeping
  topics untouched (different naming scheme, by design).
- Source reseeded (`uv run python generate.py` rerun) back to stock state:
  5000 products, 20000 offers, `offers_price_sum=1884008.69` again (matches
  ground truth), `offer_id IN (1,2,999001)` count back to 2 (999001 gone,
  1 and 2 restored) — proves the TRUNCATE+reseed in `generate.py` is a clean
  idempotent reset regardless of what a prior probe/task mutated.
- Mart: schemas only, no tables, never touched by the probe.

## Docker stack state after wave 1

Left running (`docker compose up -d` still up) for the next verification
wave — all 5 services healthy. Source is back at stock seed. No leftover
connectors, slots, publications, or `s08.*` data topics.
