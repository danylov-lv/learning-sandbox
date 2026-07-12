# Module 10 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the exact
document/event schemas, seed distributions, RNG draw order, ground-truth
semantics, and the Redis/Mongo/Postgres namespacing convention every task and
validator depends on.

This file is the shared contract for every agent working on this module (infra,
generator, task authors, validators). If you change something here, regenerate
and reverify and update every consumer in the same change.

## Stack

- **redis** `redis/redis-stack-server:7.4.0-v3`. Bundles the RedisBloom module
  (`BF.*`), which task 03 needs — a plain `redis:7` image would NOT have it. No
  password (local sandbox). Host port `6310` (`SANDBOX_10_REDIS_PORT`,
  container 6379). Healthcheck `redis-cli ping`.
- **mongodb** `mongo:7`. Root user/password `sandbox`/`sandbox`, auth DB
  `admin`; the module uses database `sandbox`. Host port `27310`
  (`SANDBOX_10_MONGO_PORT`, container 27017). Named volume `mongo-data`.
  Healthcheck `mongosh --eval "db.adminCommand('ping')"` (mongo:7 ships
  mongosh). pymongo connects with `?authSource=admin`.
- **postgres** `postgres:16`. DB/user/password all `sandbox`. Host port `54310`
  (`SANDBOX_10_PG_PORT`, container 5432). Named volume `postgres-data`.
  Healthcheck `pg_isready`. Used only by task 06 (the JSONB side).

All three reach healthy in a few seconds. `harness/common.py` holds all client
factories; every client import is lazy inside a function, so nothing needs a
live service at import time.

## Namespacing convention (MANDATED — so 8 tasks share one stack)

The three services are shared across all tasks and validators may run in
parallel. To keep them collision-free every task confines its state:

- **Redis**: all keys under prefix `s10:tNN:` (NN = zero-padded task number,
  e.g. `s10:t01:`). Validators reset with
  `redis_flush_prefix(client, "s10:tNN:")` (SCAN + DEL). **Never `FLUSHALL` /
  `FLUSHDB`** — that would wipe sibling tasks. `s10:infra:` is reserved for
  infra probes.
- **Mongo**: all collections prefixed `tNN_` (e.g. `t05_products`,
  `t06_products`, `t08_state`) inside database `sandbox`. Validators drop their
  own collections on setup.
- **Postgres** (task 06 only): all objects in a schema named `t06`. Validator
  does `DROP SCHEMA IF EXISTS t06 CASCADE; CREATE SCHEMA t06;` on setup.

## Data generation (deterministic)

`generate.py`, two independent numpy streams: products
`np.random.default_rng(10101)`, events `np.random.default_rng(10102)`.
Faker (seeded with the product seed) supplies seller display names only — a
cosmetic string that feeds NO ground-truth key. `SCALE` (env, default `1.0`)
sizes both: `n_events = round(25000 * SCALE)`,
`n_products = round(20000 * SCALE)`. The committed answer key is SCALE=1.0.
`n_events` is deliberately below `n_products / 0.70`: because a url is
`https://{domain}/p/{product_id}`, distinct urls scraped can never exceed
`n_products`, so `unique = 0.70 * n_events` must stay under 20000 for a ~30%
duplicate rate — 25000 events give 17500 unique / 7500 duplicate.

**No database is loaded by `generate.py`.** It writes three files under `data/`
and returns. Each task loads Redis / Mongo / Postgres itself (they load
differently), so DB loading is a task concern.

Output files (NDJSON — one JSON object per line):
- `data/products.json` (gitignored), `data/events.json` (gitignored)
- `data/ground-truth.json` (COMMITTED)

Time window for both `scraped_at` fields: 90 days ending 2025-06-30, i.e.
`window_start = 2025-04-02`, second resolution. `scraped_at = window_start +
day*1d + second*1s` as an ISO-8601 string.

### Product document schema (`data/products.json`)

Semi-structured is the point: `specs` keys depend on category and are randomly
absent; documents are genuinely heterogeneous.

```
{
  "product_id": int,          # 1..n_products, unique, == line order
  "url": "https://{domain}/p/{product_id}",
  "domain": str,              # one of 5 domains, Zipf-skewed
  "title": "{brand} {noun}",  # noun from a per-category pool
  "brand": str,               # from a 24-brand pool, Zipf popularity
  "category": str,            # one of the 8 categories
  "price": float,             # round(2), log-normal per category, clip >= 0.5
  "currency": str,            # USD/EUR/GBP, p = [0.60, 0.25, 0.15]
  "in_stock": bool,           # ~0.85 true
  "specs": {...},             # nested; keys depend on category, ~20% absent
  "tags": [str, ...],         # 0..4 distinct from {sale,new,bestseller,clearance,eco,imported}
  "seller": {"seller_id": int, "name": str, "rating": float},  # embedded, rating round1 in [1,5]
  "scraped_at": "YYYY-MM-DDTHH:MM:SS"
}
```

Categories (index order, also the Zipf popularity order most->least):
`[electronics, home-goods, kitchen, toys, sporting-goods, office-supplies,
beauty, apparel]`. Per-category log-normal `(median, sigma)`: electronics
120/0.9, home-goods 45/0.7, kitchen 35/0.6, toys 25/0.6, sporting-goods
55/0.7, office-supplies 15/0.5, beauty 20/0.5, apparel 30/0.6.

`specs` keys per category (each key present independently with p=0.80):
- electronics: `color, storage_gb, warranty_months`
- home-goods: `color, material, dimensions_cm`
- kitchen: `material, capacity_l, color`
- toys: `age_range, material, color`
- sporting-goods: `color, size, weight_kg`
- office-supplies: `color, pack_size, material`
- beauty: `volume_ml, scent, color`
- apparel: `color, size, material`

`color` appears in every category (pool
`[black,white,red,blue,green,silver,gray,gold]`), so the nested-color query
spans the whole catalog. Value pools for every field are in `generate.py`
(`SPEC_POOLS`).

### Event schema (`data/events.json`)

A stream of scrape hits driving dedup / streams / rate-limiter / capstone.

```
{
  "event_id": int,            # 1..n_events, == line order
  "url": str,                 # the scraped catalog product's url (fixed per product)
  "domain": str,              # the catalog product's domain (Zipf-skewed => hot domains)
  "product_id": int,          # a REAL catalog product_id (1..n_products)
  "price": float,             # round(2), catalog price * exp(N(0, 0.08)) jitter
  "in_stock": bool,
  "scraped_at": "YYYY-MM-DDTHH:MM:SS"
}
```

**Events are COUPLED to the catalog.** Each event scrapes a real product from
`data/products.json`: its `url`, `domain`, and `product_id` are that product's,
and its category (used only by ground truth) is the product's real catalog
category. Only `price` / `in_stock` / `scraped_at` are a fresh scrape
observation — `price` is the catalog price multiplied by `exp(N(0, 0.08))`, so
the LATEST scraped price per product differs from the catalog price (that
difference is exactly what the capstone materializes). A url is fixed per
product, so "duplicate url" <=> "re-scraped the same product".

**Known duplicate rate.** `n_unique = min(round(0.70 * n_events), n_products)`
DISTINCT catalog products are chosen without replacement (uniformly, so the set
of scraped products inherits the catalog's category proportions), each scraped
once ("introductions"); the remaining `n_events - n_unique` events re-scrape an
already-chosen product with a Zipf popularity weight (hot products re-scraped
more). So:
- `unique_urls = n_unique` = 17500 at scale 1.0.
- `duplicate_events = n_events - unique_urls` = 7500 at scale 1.0 (exactly
  30.0%). Order-independent: each distinct url has one first occurrence, every
  other occurrence is a duplicate, regardless of stream order.
- `unique_urls <= n_products` always (a url exists only for a catalog product),
  which is why `n_events` is capped at 25000 (see the SCALE note above).

### RNG draw order — DO NOT REORDER without regenerating everything

`build_products(seed, n)` (seed 10101):
- P1 `category_idx = rng.choice(8, p=cat_weights)` — Zipf `1/rank^1.1`.
- P2 `domain_idx = rng.choice(5, p=domain_weights)` — Zipf `1/rank^1.1`.
- P3 `brand_idx = rng.choice(24, p=brand_weights)` — Zipf `1/rank^1.05`.
- P4 `z = rng.normal()` -> `price = round(exp(ln(median_cat)+sigma_cat*z),2)`.
- P5 `currency_idx = rng.choice(3, p=[.6,.25,.15])`.
- P6 `in_stock = rng.random() < 0.85`.
- P7 `seller_id = rng.integers(1, 201)` (200 sellers).
- P8 `seller_rating = round(1 + rng.random()*4, 1)`.
- P9 `day = rng.integers(0, 90)`; P10 `second = rng.integers(0, 86400)`.
- P11 `n_tags = rng.integers(0, 5)` (0..4).
- P12 `tag_rand = rng.random((n, 6))` — argsort per row, take first `n_tags`
  as the selected tag indices (distinct), then sort by pool index.
- P13 `spec_presence = rng.random((n, 3))` — key present iff `< 0.80`.
- P14 `spec_value = rng.random((n, 3))` — value index `floor(u * len(pool))`.
- P15 `title_noun_idx = rng.integers(0, 5)`.

`build_events(seed, n, products)` (seed 10102),
`n_unique = min(round(0.70*n), n_products)`, `n_dup = n - n_unique`. Indices
below are 0-based positions into `products`:
- E1 `intro_pos = rng.choice(n_products, size=n_unique, replace=False)` — the
  distinct scraped products (uniform => inherits catalog category mix).
- E2 `pop_rank = rng.permutation(n_unique)+1` -> Zipf `1/rank^1.1` popularity
  weight over the introduced set (for re-scrape draws).
- E3 `dup_pick = rng.choice(n_unique, size=n_dup, p=pop_weight)`.
- E4 `all_pos = concat(intro_pos, intro_pos[dup_pick])[rng.permutation(n)]` —
  stream shuffle; `event_id` assigned 1..n by final position.
- E5 per event: `noise = rng.normal(0, 0.08)` -> `price = round(catalog_price *
  exp(noise), 2)`; `in_stock = rng.random() < 0.85`.
- E6 `day = rng.integers(0,90)`; `second = rng.integers(0,86400)`.

`build_events` needs the catalog, so it takes the `products` list (unlike the
original `(seed, n)` signature). A validator wanting an in-memory event
workload calls `build_products(10101, n_products)` first and passes the result.

## `data/ground-truth.json` (committed answer key, SCALE=1.0)

Computed by `_ground_truth` by iterating the built product/event dicts (small:
20k/25k), so it matches exactly what a task loads. Keys:

- `seed` `{products:10101, events:10102}`, `scale`, `n_products`, `n_events`,
  `categories` (the 8), `row_counts` `{products, events}`.
- `per_category`: `{cat: {count, avg_price(round2), in_stock_count}}` over
  PRODUCTS.
- `top_brands`: top 10 `[[brand, count], ...]`, descending by product count,
  ties broken by brand name ascending.
- `graded_query` (tasks 05/06 document query): in-stock products in category
  `electronics` whose `tags` contains `sale`. Emits
  `{category:"electronics", tag:"sale", in_stock:true, count, product_ids}`
  where `product_ids` is the full sorted list (a couple thousand ints — fine to
  commit).
- `nested_query` (Mongo-vs-JSONB nested match): products where
  `specs.color == "black"`. Emits `{path:"specs.color", value:"black", count}`.
- `price_sum`: round-2 sum of `price` over all products.
- `events`: `{total, unique_urls, duplicate_events, per_domain:{domain:count}}`
  over the event stream. `per_domain` is Zipf-skewed (hot domains for the rate
  limiter).
- `current_state` (capstone answer key, event-derived):
  `{count, price_sum(round2), per_category_count:{cat:int}}`. `count` = distinct
  scraped product_ids (== `unique_urls`). `price_sum` = sum over those products
  of the LATEST scraped price, where "latest" is max by `(scraped_at,
  event_id)`. `per_category_count[cat]` = distinct scraped products whose real
  catalog category is `cat` — so it inherits the catalog's Zipf category skew
  (NOT uniform), scaled by the ~87.5% of products that get scraped. The capstone
  grades the learner's Mongo materialization (latest price + per-category counts
  of scraped products) against these exact numbers, and `price_sum` differs
  from the catalog `price_sum` precisely because scrapes re-observe prices.

Verified values at SCALE=1.0 (see `notes-infra.md`):
`per_category.electronics={count:7865, avg_price:177.86, in_stock_count:6704}`;
`top_brands[0]=["Acme",5619]`; `graded_query.count=2276`;
`nested_query.count=2052`; `price_sum=1933648.95`;
`events={total:25000, unique_urls:17500, duplicate_events:7500 (30.0%)}`,
`per_domain.shopmart.example=10453` (skewed, hot domain);
`current_state={count:17500, price_sum:1700991.53,
per_category_count electronics:6866 ... apparel:705}`.

All money is rounded to 2 decimals. Validators must compare floats with a small
tolerance, never exact-decimal equality.

## Pure functions for validators

`build_products(seed, n)` and `build_events(seed, n, products)` are pure
(numpy/python + Faker text only, no DB, no file I/O) and return lists of dicts,
so a validator can synthesize a deterministic in-memory workload without reading
the data files (mirrors module 09's `build_duplicate_batch`). Because events are
coupled to the catalog, `build_events` takes the `products` list: call
`build_products(10101, n_products)` then `build_events(10102, n_events,
products)` with the scaled counts to reproduce the committed corpus exactly.
