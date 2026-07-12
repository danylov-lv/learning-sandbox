# Module 10 infra notes (wave-1 build + verification)

Host: Windows 11, Git Bash, Docker Desktop (linux/amd64 containers), uv 0.10.9,
Python via `uv run`.

## Images actually pulled

- `redis/redis-stack-server:7.4.0-v3` (image id 7d8e657d60d5, 294MB) — the
  requested tag pulled cleanly; **no fallback to `:latest` needed**. Bundles
  RedisBloom (`BF.*`), verified below.
- `mongo:7` (image id d5b3ca8c3f3c, 294MB) — ships `mongosh`, used by both the
  healthcheck and the pymongo connectivity probe.
- `postgres:16` (image id 21f6013073bc, 160MB).

## Commands run

```
uv sync                       # 14 packages installed; uv.lock written
docker compose up -d          # pulled mongo:7, created 3 containers + 2 volumes
docker compose ps             # polled; all three healthy on first check (~<3s after up)
uv run python generate.py     # SCALE=1.0, ~1.4s wall
```

Dependency versions resolved by `uv sync` (into `uv.lock`): redis 8.0.1,
pymongo 4.17.0, psycopg 3.3.4 (+ psycopg-binary), numpy 2.5.1, faker 40.28.1,
pytest 9.1.1 (plus transitive dnspython, tzdata, colorama, etc.).

## Healthy stack (docker compose ps)

```
10-nosql-patterns-mongodb-1   mongo:7                              healthy
10-nosql-patterns-postgres-1  postgres:16                          healthy
10-nosql-patterns-redis-1     redis/redis-stack-server:7.4.0-v3    healthy
```

## Connectivity + RedisBloom probe (throwaway script, since deleted)

Via `harness/common.py` clients:
- `redis_client().ping()` -> True
- `mongo_client().admin.command("ping")` -> ok 1.0 (pymongo with
  `?authSource=admin`)
- `pg_connect()` + `SELECT 1` -> 1
- RedisBloom on `s10:infra:probe`: `BF.RESERVE 0.01 1000` -> OK; `BF.ADD` a url
  -> True; `BF.EXISTS` seen -> True, unseen -> False; key then deleted. **This
  proves task 03's `BF.*` path works on the shipped image.**

After the probe, `redis-cli --scan --pattern 's10:*'` returned 0 keys and the
Mongo `sandbox` database had 0 collections — no stray probe state left behind.

## generate.py verification (SCALE=1.0)

- Wrote `data/products.json` (20000 lines, NDJSON), `data/events.json` (25000
  lines, NDJSON), `data/ground-truth.json` (committed).
- **Deterministic**: two consecutive runs produced a byte-identical
  ground-truth.json (sha256 `38b7309b...ce2ac8`). Wall time ~1.4s (no DB
  touched).
- Key ground-truth numbers:
  - `row_counts` = {products: 20000, events: 25000}
  - `price_sum` (products) = 1933648.95
  - `per_category.electronics` = {count 7865, avg_price 177.86, in_stock 6704}
  - `top_brands[0]` = ["Acme", 5619]
  - `graded_query.count` = 2276 (electronics + in_stock + "sale" tag)
  - `nested_query.count` = 2052 (specs.color == "black")
  - `events.unique_urls` = 17500, `events.duplicate_events` = 7500 (exactly
    30.0%), `per_domain` Zipf-skewed (shopmart 10453 -> bargainbay 1727)
  - `current_state` = {count 17500, price_sum 1700991.53,
    per_category_count electronics 6866, home-goods 3318, kitchen 2091, toys
    1507, sporting-goods 1170, office-supplies 1017, beauty 826, apparel 705}
    — non-uniform, inherits the catalog's Zipf category skew.
  - Verified (in-memory) that every event url belongs to a catalog product.

## Gotchas / decisions

- **Events are coupled to the catalog.** Each event scrapes a real product from
  `data/products.json` (url/domain/product_id/category from the catalog;
  price = catalog price * exp(N(0, 0.08)), plus fresh in_stock/scraped_at). ~70%
  of events scrape a not-yet-seen product (chosen without replacement, so the
  scraped set inherits the catalog category mix), the rest re-scrape a hot
  product (Zipf) — giving exactly 30% duplicate urls. Because a url only exists
  for a catalog product, `unique_urls <= n_products = 20000`; that is why
  `n_events` is 25000 (0.70 * 25000 = 17500 unique urls). `build_events` takes
  the `products` list (signature `build_events(seed, n, products)`).
  `current_state.per_category_count` is now non-uniform (inherits catalog skew),
  and its `price_sum` differs from the catalog `price_sum` because scrapes
  re-observe prices — the point of materializing current state.
- **pymongo auth**: connect string needs `?authSource=admin` (root user lives
  in admin); without it `admin.command('ping')` still works but querying the
  `sandbox` db would fail auth. `mongo_uri()` in common.py bakes it in.
- **mongosh present** in mongo:7, so the healthcheck uses `mongosh` (no `mongo`
  fallback needed).
- **`bc` is absent** in this Git Bash; timed generate.py via python instead.
- Stack left **running** for the task-authoring wave. Named volumes
  `10-nosql-patterns_mongo-data` and `10-nosql-patterns_postgres-data` persist
  Mongo/Postgres data across restarts; Redis is in-memory (no volume, by
  design — it holds only transient task state).
