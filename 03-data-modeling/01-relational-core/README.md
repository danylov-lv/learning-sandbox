# 01 — Relational Core

## Backstory

PriceWatch has been running on raw JSONL dumps for a year: every scrape, every
admin action, every price change, appended to `data/events.jsonl` in arrival
order. It works, in the sense that nothing has caught fire, but nobody can
answer "how many listings does shop S014 have right now" without replaying
2.3M lines in a Python loop. You're hired to give the platform an actual OLTP
database: shops, products, listings, price observations, with the constraints
that make bad data impossible to insert instead of merely inconvenient to
query.

The event stream itself won't go away — later tasks in this module keep
mining it for history you haven't modeled yet — but the day-to-day app needs
a normalized schema it can query directly, and a loader that gets the stream
into it correctly.

## What's given

- A running Postgres 16 at `localhost:${SANDBOX_03_PORT:-54303}` (db/user/pass
  `sandbox`), started with `docker compose up -d` from the module root.
- `data/events.jsonl` — 2,336,793 event lines, ordered by `ingested_at`
  (arrival order, not business time). Regenerate with
  `uv run python harness/events.py` (seed 42, ~2 minutes) if the file is
  missing; it's gitignored.
- `data/clients.jsonl` — client-to-tracked-product rows, one line per
  (client, product) pair.
- Event types and their fields (verify against `harness/events.py` if in
  doubt — its module docstring and `main()` are safe to read; the row-building
  code is not needed):
  - `shop_registered {shop_code, name, country, tier, home_currency, event_time, ingested_at}`
  - `shop_renamed {shop_code, new_name, event_time, ingested_at}`
  - `shop_tier_changed {shop_code, new_tier, event_time, ingested_at}`
  - `product_discovered {shop_code, product_code, local_title, canonical_title, brand, category, event_time, ingested_at}`
  - `product_attrs_changed {product_code, changes: {field: value}, event_time, ingested_at}`
  - `product_delisted {shop_code, product_code, event_time, ingested_at}`
  - `product_relisted {shop_code, product_code, local_title, event_time, ingested_at}`
  - `price_observed {shop_code, product_code, price, currency, event_time, ingested_at}`
- Generator guarantees you may rely on: `shop_registered` for a shop arrives
  before any other event for that shop; `product_discovered` for a
  (shop, product) listing arrives before that listing's price observations;
  admin events for the same entity arrive in `event_time` order relative to
  each other; no two distinct prices share the same
  (shop_code, product_code, event_time).
- `src/schema.sql` — header-comment stub: your DDL goes here.
- `src/load.py` — header-comment stub: your loader goes here.
- `src/q01.sql` .. `src/q04.sql` — stubs, one per question below.

## What's required

1. Design a normalized schema in `src/schema.sql` covering shops, products,
   listings (the shop/product relationship, with its own lifecycle), and
   price observations. You choose the tables, keys, and constraints — there
   is no prescribed table list. Two things the schema must support:
   - **Lossless capture.** Keep both `event_time` and `ingested_at` on
     observations (they diverge for ~3% of rows — late arrivals), and both
     the original `price`/`currency` and enough to convert to USD. Later
     tasks in this module reuse this database; a schema that only keeps
     "current price in USD" will actively hurt you there.
     Whatever currency-conversion approach you pick, it must be reproducible
     from the FX table in `harness/common.py` — don't hardcode converted
     amounts.
   - **Cheap current-state queries.** q01 below asks for the currently active
     listing count per shop. That must not require scanning or replaying the
     full observation history — think about what state a listing needs to
     carry directly.
2. Write `src/load.py` to parse `data/events.jsonl` and `data/clients.jsonl`
   and populate your schema. 2.3M lines is not huge, but a naive
   row-by-row `INSERT` will take a long time — use `COPY` or batched inserts
   and aim for minutes, not hours. Handle the ~1% exact-duplicate
   observations at load time (see q03).
3. Answer four questions in `src/q01.sql`..`src/q04.sql`, run against your
   loaded schema:
   - **q01** — number of currently active listings per shop, at the end of
     the stream. Columns: `(shop_code, active_listings)`. A listing is active
     from its `product_discovered` event, inactive from `product_delisted`,
     active again from `product_relisted`.
   - **q02** — latest observation per (shop, product) for a fixed set of ten
     products: `P00001, P01996, P01001, P00004, P00998, P01995, P01000,
     P01999, P00002, P00999`. Columns: `(product_code, shop_code, event_time,
     price_usd)`.
   - **q03** — deduplicated observation counts by currency, plus one `ALL`
     row with the grand total. Columns: `(currency, observation_count)`.
     This is the check that your loader actually deduplicated
     (shop_code, product_code, event_time) correctly, keeping the
     first-arriving copy.
   - **q04** — daily min/max/avg USD price for product `P00001` over the
     60 days starting `2025-01-01`. Columns: `(day, min_price_usd,
     max_price_usd, avg_price_usd)`.

## Completion criteria

```
uv run python 01-relational-core/tests/check.py
```

or directly:

```
uv run python harness/validate.py --task 01
```

All four questions must print `PASSED`.

## Estimated evenings

2

## Topics to read up on

- Normalization and natural keys vs. surrogate keys
- Slowly-changing vs. append-only data and how to tell them apart in a schema
- `COPY` vs. batched `INSERT` performance in Postgres
- Deduplication strategies: unique constraints with `ON CONFLICT`, staging
  tables, window functions (`ROW_NUMBER()` / `DISTINCT ON`)
- `jsonb` extraction functions in Postgres
