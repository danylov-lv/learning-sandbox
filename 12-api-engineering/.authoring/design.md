# Module 12 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
shared harness API every task and validator depends on, the `shop` schema +
RNG draw order + committed ground-truth values, the fixture-password rule,
the per-task namespacing scheme, and the verification philosophy per task
type. This file is the shared contract for every agent working on this
module (infra, generator, task authors, validators). If you change
something here, regenerate and reverify and update every consumer in the
same change.

This is the WAVE-1 infrastructure build: docker-compose, pyproject/uv.lock,
generate.py, and harness/. No task directories exist yet (01-09 + capstone
are authored in a later wave against this infra) — there is nothing here to
spoil yet except the corpus and harness contract itself, but the file is
named/marked consistently with every other module's `.authoring/design.md`.

## Own stack, not module 02's — decision and rationale

Module 12 runs its OWN Postgres + Redis, seeded with the SAME marketplace
domain (sellers/categories/products/users/orders/order_items) as module 02,
but through a **clean, properly-indexed** schema, in schema `shop`.

Module 02's Postgres (`02-sql-optimization`) is deliberately wrecked — see
`02-sql-optimization/seed/schema.sql` and its `.authoring/` — with planted
defects (missing indexes, wrong column types, autovacuum sabotage, index
bloat) that ARE that module's curriculum. Module 12 is about a different
layer entirely: pagination, caching, rate limiting, background jobs,
streaming, auth, secrets, and a SQL-injection drill — API-layer concerns,
not query-plan archaeology. Reusing module 02's container would mean either
(a) the API tasks silently inherit module 02's slow paths and every
pagination/caching benchmark becomes contaminated by unrelated missing-index
noise, or (b) module 12 would need to "fix" module 02's schema in place,
destroying module 02's own curriculum for any learner doing both modules.
Neither is acceptable, so module 12 gets its own container, own ports, own
generator, own committed ground truth — fully independent of module 02's
lifecycle (a learner can nuke and reseed module 02 at SCALE=0.1 without
touching module 12 at all, and vice versa).

The one deliberate exception: task 09 (load-test bottleneck hunt) still
needs a *plausible* slow path to hunt for. That slow path will be an
**application-layer** problem authored later (N+1 queries from the FastAPI
code, a blocking driver call inside an async handler, an unbounded
connection pool) — never a missing index. The `shop` schema itself stays
clean for the entire module; see "Clean indexing" below.

## No fixed API port

Task apps (FastAPI/uvicorn) run on the HOST, not in docker-compose.
`harness/service.py` always binds `127.0.0.1:0` (OS-assigned ephemeral
port) for both the in-process and subprocess launch strategies — there is
no `SANDBOX_12_API_PORT` anywhere and none should ever be added; parallel
task runs (and parallel validator runs within one task) must never
collide on a port. Only Postgres and Redis have fixed, env-overridable
host ports (`CONVENTIONS.md`):

| Service  | Host port | Env var                  |
|----------|-----------|---------------------------|
| Postgres | 54312     | `SANDBOX_12_PG_PORT`      |
| Redis    | 6312      | `SANDBOX_12_REDIS_PORT`   |

## Namespacing scheme (the stack is SHARED across parallel task runs)

- **Postgres**: schema `shop` is the SHARED READ-ONLY corpus. **No task may
  write to `shop`** — not a row, not a column. A task needing writable
  state (background job records, auth/session tables, SQLi-drill tables)
  creates and owns its own schema `tNN` (e.g. `t04`, `t07`). Task 06
  (SQL injection) additionally owns per-task Postgres ROLES named `t06_*`
  for its least-privilege-role exercise.
- **Redis**: every key a task writes is prefixed `s12:tNN:` (e.g.
  `s12:t02:cache:...`, `s12:t03:quota:...`). Cleanup is ALWAYS
  `redis_flush_prefix(client, "s12:tNN:")` (SCAN + DEL) — **never
  FLUSHALL/FLUSHDB**, since other tasks' validators may be running
  concurrently against the same Redis instance.
- **API ports**: always ephemeral via `harness/service.py`, never hardcoded.
- **Idempotent re-runs**: a validator that creates a `tNN` schema or `s12:tNN:`
  keys must drop/flush its OWN namespace on setup (not teardown only), so a
  crashed previous run never blocks a fresh one.

## Harness API

Every third-party import (`psycopg`, `psycopg_pool`, `redis`, `uvicorn`,
`httpx`, `tracemalloc`) is lazy inside the function that needs it;
importing any `harness.*` module has zero side effects and requires nothing
running.

### `harness/common.py`

```python
MODULE_ROOT: Path                    # 12-api-engineering/
DATA_DIR: Path                       # MODULE_ROOT / "data"
GROUND_TRUTH_PATH: Path              # DATA_DIR / "ground-truth.json"

PG_DEFAULT_PORT = 54312
REDIS_DEFAULT_PORT = 6312
PG_DB = PG_USER = PG_PASSWORD = "sandbox"
SHOP_SCHEMA = "shop"
SEED = 121212                        # canonical corpus seed; generate.py imports this
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 1024, 8, 1, 32

def not_passed(reason) -> NoReturn   # print "NOT PASSED: <reason>", sys.exit(1)
def passed(msg="") -> NoReturn       # print "PASSED[: msg]", sys.exit(0)
def guarded(fn) -> Callable          # decorator: unexpected exceptions (incl. NotImplementedError) -> NOT PASSED; SystemExit re-raised
def _last_line(text) -> str          # last non-empty line of a stream/error text

def time_it(fn, *a, **k) -> tuple        # (result, elapsed_seconds) via time.perf_counter
def write_baseline(path, obj) -> Path    # write gitignored *-local.json under MODULE_ROOT
def read_baseline(path) -> dict | None   # read it back, or None if absent

def load_ground_truth() -> dict      # reads GROUND_TRUTH_PATH or NOT PASSED("...run generate.py first")

def run_async(coro) -> Any           # asyncio.run(coro); NOT PASSED if a loop is already running

def measure_peak_memory(fn, *a, **k) -> tuple   # (result, peak_bytes) via tracemalloc around a SYNC call

def pg_port() -> int
def pg_dsn() -> str                  # "host=... port=... dbname=sandbox user=sandbox password=sandbox"
def pg_conn() -> psycopg.Connection  # live connection, or NOT PASSED
def pg_pool(min_size=1, max_size=10, **kwargs) -> psycopg_pool.ConnectionPool  # opened, or NOT PASSED

def redis_port() -> int
def redis_client(decode_responses=True) -> redis.Redis   # pinged, or NOT PASSED
def redis_flush_prefix(client, prefix) -> int             # SCAN+DEL count; NEVER FLUSHALL

def build_password(user_id) -> str                  # "pw-<id>-kupitron"
def hash_password(password, salt: bytes) -> str      # "scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>"
def verify_password(password, stored: str) -> bool   # False (never raises) on malformed `stored`
def build_user_password_hash(user_id) -> str         # hash_password(build_password(id), salt-for-id)
```

Design notes:

- **`measure_peak_memory` takes a SYNC callable**, unlike module 11's
  `async_fn`-specific version — module 12's fn under test is not always a
  coroutine (task 05 streaming may measure a sync generator's memory
  footprint, or a small wrapper that internally calls `run_async(...)`
  itself). If you need to measure async code, wrap it: `measure_peak_memory
  (lambda: run_async(my_coro()))`.
- **`pg_pool`** returns the pool CLOSED-then-opened via `.open(wait=True,
  timeout=10)` inside a `try/except` that converts any failure to
  `NOT PASSED` — callers use it as a context manager
  (`with pg_pool() as pool: ...`) exactly like `psycopg_pool.ConnectionPool`
  itself, since that class is already a context manager.
- **`pg_conn`** returns a live `psycopg.Connection` directly (also usable as
  `with pg_conn() as conn: ...` — psycopg3 connections are context managers
  natively), matching every prior module's `pg_connect`-style helper, just
  renamed `pg_conn` per this module's spec.
- **Fixture passwords are NOT a security posture.** `SCRYPT_N=1024` (vs. the
  2**14+ recommended for a real login system) is chosen ONLY so seeding
  20,000 users finishes in well under a minute (see notes-infra.md for the
  actual benchmark that drove this choice: n=2048 took ~70s threaded, n=1024
  ~35s, both were tested before picking 1024 for extra headroom against the
  "couple of minutes total" generation budget). `build_password(user_id)`
  is a PURE function (`f"pw-{user_id}-kupitron"`) — any task author or
  validator can log in as seeded user N without touching the DB at all:
  `build_password(42)` gives the plaintext, and a login endpoint's own
  bcrypt/scrypt-equivalent check against the stored `password_hash` (which
  the learner's login code queries) should succeed. The stored hash itself
  is reproducible byte-for-byte from `build_user_password_hash(user_id)`,
  which derives its salt as `sha256(f"{SEED}:user:{user_id}")[:16]` — pure
  and deterministic, no DB round-trip needed to know what SHOULD be stored.

### `harness/service.py`

```python
class Service:
    base_url: str                    # "http://127.0.0.1:<port>"
    port: int
    def client(self, **kwargs) -> httpx.AsyncClient   # bound to base_url

@asynccontextmanager
async def run_app(app_or_import_string, *, host="127.0.0.1", startup_timeout=10.0, **uvicorn_kwargs) -> AsyncIterator[Service]

@asynccontextmanager
async def run_app_subprocess(import_string, *, host="127.0.0.1", extra_args=None, env=None, startup_timeout=15.0) -> AsyncIterator[Service]

@asynccontextmanager
async def asgi_client(app, *, base_url="http://testserver", **kwargs) -> AsyncIterator[httpx.AsyncClient]
```

- **Port-binding strategy for `run_app` (in-process)**: bind our OWN
  `socket` to `(host, 0)` FIRST, read the assigned port immediately via
  `sock.getsockname()`, THEN hand that socket to
  `uvicorn.Server.serve(sockets=[sock])`. This is the same rationale module
  11's mock peer used for `aiohttp.web.SockSite`: the port is known before
  any uvicorn-internal server object exists, so there is no dependency on
  uvicorn's internal `Server.servers[...].sockets` attribute shape across
  versions. Startup is awaited via polling `server.started` (uvicorn sets
  this `True` once its lifespan startup completes) with a `startup_timeout`
  safety net that re-raises the server task's own exception if it exited
  early (e.g. the learner's app crashes on import).
- **Port strategy for `run_app_subprocess` (real separate process)**:
  bind-then-close-then-hand-the-port-number-to-the-child. A real child
  process cannot simply inherit our pre-opened socket the portable way
  `run_app` does in-process (socket handle inheritance across processes is
  not simple/portable on Windows), so instead we bind `(host, 0)` to learn a
  free port, IMMEDIATELY close it, and launch `python -m uvicorn
  <import_string> --host <host> --port <port>` targeting that port number.
  This is a small time-of-check/time-of-use race (another process could
  grab the port in the gap) — acceptable for test infra, where a collision
  is rare and, if it ever happens, surfaces as a clear
  `TimeoutError`/`RuntimeError` from the startup-poll loop rather than a
  silent misbehavior. Startup is detected by polling a raw TCP connect
  (not an HTTP request — the harness doesn't know the app's routes).
  `import_string` MUST be an "module:attr" string here (unlike `run_app`,
  which also accepts a live app object) since a subprocess needs something
  importable.
- **`asgi_client`** wraps `httpx.ASGITransport` directly — no socket, no
  subprocess, fastest option for validators that only assert response
  shape/content and don't need real TCP/timing behavior. This is the
  RECOMMENDED default for most correctness checks; reach for `run_app` when
  a test genuinely needs a real socket (e.g. testing connection-level
  behavior, streaming under real backpressure) and `run_app_subprocess`
  only for task 09 (load test — real HTTP + OS scheduling overhead, not
  coroutine hand-off inside the validator's own event loop) and task 04
  (background worker that must be observable independent of the
  validator's own event loop/process).

### `harness/load.py`

```python
@dataclass
class LoadResult:
    total: int; ok: int; errors: int
    rps: float; p50_ms: float; p95_ms: float; p99_ms: float
    elapsed_s: float

async def bombard(url_or_fn, *, concurrency=10, duration_s=None, requests=None,
                   method="GET", client_kwargs=None, request_kwargs=None) -> LoadResult
```

- `url_or_fn` is either a `str` URL (workers share one `httpx.AsyncClient`)
  or an async callable `async def () -> response-like` (each worker awaits
  it directly — the callable owns its own client/headers/auth; only needs a
  `.status_code` attribute on whatever it returns to be graded success/error).
- Exactly one of `duration_s` / `requests` must be given (raises
  `ValueError` otherwise — an authoring-time contract violation, not a
  learner-code condition, so it is NOT converted to `NOT PASSED`).
- Percentiles are linear-interpolation over the actually-collected latency
  sample (same convention as `numpy.percentile`'s default) — "honest"
  in the sense the SPEC asked for, not a theoretical distribution fit.
- A request that raises any exception counts as an error, not a crash of
  the whole run — `bombard()` always returns a `LoadResult`, even under
  100% error rate.
- No locust dependency, per the SPEC's explicit choice of "a simple asyncio
  bombardier" over locust.

## Fixture passwords — the exact rule

- Plaintext: `build_password(user_id) == f"pw-{user_id}-kupitron"` — a PURE
  function of the integer id. This is fixture data for exercises (JWT auth
  flows, login trap tests), NOT a security claim; never reuse this pattern
  for real credentials.
- Salt: `sha256(f"{SEED}:user:{user_id}")[:16]` (16 bytes), deterministic
  per user given the canonical `SEED = 121212` — reruns of `generate.py`
  produce byte-identical `password_hash` values.
- Stored format: `scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>` with
  `n=1024, r=8, p=1, dklen=32` (see harness.common's SCRYPT_* constants).
- `hash_password`/`verify_password`/`build_user_password_hash` in
  `harness/common.py` are the single source of truth — task authors and
  validators must call these rather than re-deriving the format.

## Corpus + ground truth (`generate.py`)

Every `build_*` function is PURE (numpy + stdlib only, no file/DB I/O) and
INDEPENDENTLY seeded (not one shared threaded rng across the whole corpus)
so a validator can synthesize any single table's in-memory data without
replaying every other table's draws first — mirrors module 10's pure-builder
pattern, one level more granular (module 10 had two pure builders; module 12
has one per table).

```python
SEED = 121212           # harness.common.SEED, canonical
SEED_SELLERS = 121213
SEED_PRODUCTS = 121215
SEED_USERS = 121216
SEED_ORDERS = 121217
SEED_ORDER_ITEMS = 121218

def build_categories() -> list[dict]                              # pure, NO rng (fixed literal tree)
def build_sellers(seed, n) -> dict[str, array]                      # id, name, tier, rating, created_at
def build_products(seed, n, n_sellers, leaf_ids) -> dict[str, array]  # id, seller_id, category_id, title, price, in_stock, attrs, created_at, updated_at
def build_users(seed, n, compute_password_hash=True) -> dict[str, array]  # id, email, full_name, country, password_hash, created_at
def build_orders(seed, n, n_users) -> dict[str, array]              # id, user_id, status, created_at (NO total_amount)
def build_order_items(seed, order_ids, product_ids, product_prices) -> (dict[str, array], order_total_array)
```

### Row counts (SCALE=1.0)

| table              | rows (SCALE=1.0) | scales with SCALE? |
|--------------------|-------------------|---------------------|
| shop.sellers       | 2,000             | yes                 |
| shop.categories    | 60 (8 roots + 52 leaves) | NO — fixed lookup tree |
| shop.products      | 200,000           | yes                 |
| shop.users         | 20,000            | yes                 |
| shop.orders        | 500,000           | yes                 |
| shop.order_items   | 1,188,048 (~1.2M) | yes (derived from orders) |

`order_items` is NOT independently scaled — it is derived per-order via
`items_per_order` (1..5, weighted `[.30,.30,.20,.12,.08]`, expectation
~2.38/order), so its count is `sum(items_per_order)` and only
approximately `2.4 * n_orders`, matching the SPEC's "~1,200,000".

### Category tree

8 families (`FAMILIES` in `generate.py`): electronics, home-goods, kitchen,
toys, sporting-goods, office-supplies, beauty, apparel. Each family gets one
depth-0 root (`name` = title-cased family) and depth-1 leaves (7 each for
the first four families, 6 each for the last four — `7*4 + 6*4 = 52`).
`build_categories()` assigns ids 1..60 in a FIXED order with NO randomness:
roots 1..8 (FAMILIES order), then leaves 9..60 grouped by family (FAMILIES
order) with each family's own leaves in `LEAF_NAMES[family]` order. So, at
SCALE=1.0: category id 9 = "Headphones & Audio" (electronics' first leaf) —
the single most popular leaf globally (see Zipf ranking below), confirmed
live: `per_category_product_count["9"] == 52169` products, the largest of
any leaf.

Products are assigned ONLY to leaf (depth=1) categories, never to a root —
`per_category_product_count` is 0 for every root id (1..8) in the committed
ground truth, by construction.

### RNG draw order (do not reorder without regenerating + updating every consumer)

**`build_sellers(seed, n)`** — SL1..SL6, in this order:
`SL1` word-1 index, `SL2` word-2 index (both for `name`), `SL3` tier index
(`p=[.50,.30,.15,.05]` over bronze/silver/gold/platinum), `SL4` rating
(`clip(normal(4.2, 0.4), 1.0, 5.0)`, rounded 2dp), `SL5` account-window day,
`SL6` account-window second-of-day.

**`build_products(seed, n, n_sellers, leaf_ids)`** — P1..P13:
`P1` leaf position (Zipf, `p=category_weights()`, rank = leaf's position in
the global 52-leaf order, `w = 1/(rank+1)**1.1`), `P2` a seller-popularity
PERMUTATION (`rng.permutation(n_sellers)+1`, ranked, `w = 1/rank**1.2`) —
this is what makes some sellers list far more products than others, `P3`
seller_id (Zipf-weighted choice using P2's weights), `P4` a standard-normal
`z` for the lognormal price (`median`/`sigma` per FAMILY of the product's
leaf, from `CATEGORY_PRICE_PROFILE`, clipped `>= 0.5`, rounded 2dp), `P5`
`in_stock` (`p=0.88`), `P6` created-day (cyclical/seasonal weighted, see
`day_weights()` below, over the 548-day window), `P7` created-second-of-day,
`P8` `updated_at` delta-days (`0..90`, added to `created_at`, clipped at
the window end), `P9` brand index (uniform over 24 brands, always present in
`attrs`), `P10` title adjective index (uniform over 10 adjectives), `P11`
a `(n, 3)` "is this family-attr slot present" array (`p=0.75` per slot),
`P12` a `(n, 3)` "which pool value" array, `P13` — INSIDE a fixed-order loop
over `FAMILIES` (boolean-masked per family, mirroring module 08's
per-category title-building loop) — a noun-index draw sized to that
family's matched-row count, used with `P9`'s adjective to build `title`.
`attrs` assembly (brand + up to 3 optional family-specific fields from
`FAMILY_ATTR_FIELDS`/`ATTR_POOLS`, present per `P11`/`P12`) happens in a
plain Python loop after all vectorized draws, in row order 0..n-1 (no
further rng consumption).

**`build_users(seed, n, compute_password_hash=True)`** — U1..U5:
`U1` first-name index, `U2` last-name index, `U3` country index (UNIFORM
over 15 countries — no Zipf skew here, unlike categories/sellers; a
deliberate simplification since the SPEC only calls out Zipf for category
and seller popularity), `U4` account-window day, `U5` account-window
second-of-day. Password hashing (if `compute_password_hash=True`) happens
AFTER these draws via `_build_password_hashes(ids)` — it does NOT consume
the numpy `rng` at all (salts are derived from `SEED` + user id via
`hashlib.sha256`, independent of the numpy stream).

**`build_orders(seed, n, n_users)`** — O1..O4:
`O1` `user_id` (uniform `1..n_users` — no popularity skew on who orders more;
another deliberate simplification, not called out in the SPEC as needing
Zipf), `O2` status index (`p=[.50,.27,.08,.05,.06,.04]` over
completed/shipped/processing/pending/cancelled/refunded), `O3` created-day
(same cyclical/seasonal `day_weights()` as products, over the SAME 548-day
window), `O4` created-second-of-day. `total_amount` is deliberately NOT
drawn here — see `build_order_items`.

**`build_order_items(seed, order_ids, product_ids, product_prices)`** — I1..I4:
`I1` `items_per_order` per order (`1..5`, `p=[.30,.30,.20,.12,.08]`,
E[items] ≈ 2.38), `I2` a product-popularity PERMUTATION over ALL products
(`rng.permutation(n_products)+1`, `w = 1/rank**1.15`) — hot-seller demand,
independent of `build_products`' P2/P3 seller-popularity permutation (a
product's category/seller popularity and its ORDER demand are drawn from
unrelated distributions on purpose — a niche product can still sell well),
`I3` `product_pos` per line item (weighted choice using I2's weights),
`I4` `qty` per line item (`1..5`, `p=[.55,.25,.12,.05,.03]`). `unit_price`
is NOT an independent draw — it is looked up from `product_prices` at the
chosen `product_pos`, so `shop.order_items` is always internally consistent
with `shop.products.price` (no unit_price drift). `order_total_amount` is
then `bincount`-summed as `sum(qty * unit_price)` grouped by `order_id`,
rounded 2dp — this is exactly `orders.total_amount`, computed FROM the
items, never an independent draw. Verified live:
`orders_total_sum == sum(qty*unit_price over all order_items)` to the cent
(`307483851.66` both ways, see notes-infra.md).

### `day_weights(n_days, start_weekday)`

Cyclical/seasonal weighting shared by `build_products` and `build_orders`
(both draw `created_at` over the identical 548-day window,
`WINDOW_START..WINDOW_END`): `weekly = 1.15 if weekend else 1.0`,
`trend = 1.0 + 0.15 * (day / (n_days-1))` (gentle upward drift over the
window), `seasonal = 1.0 + 0.10 * sin(2*pi*day/365)` (annual cycle),
combined multiplicatively and normalized to a probability vector.

### Time windows (fixed reference dates, independent of wall-clock "today")

- `WINDOW_END = 2026-06-30`, `WINDOW_DAYS = 548` (~18 months) →
  `WINDOW_START = 2024-12-30`. Used for `shop.products.created_at`/
  `updated_at` and `shop.orders.created_at`.
- `ACCOUNT_WINDOW_DAYS = 1095` (3 years), same `WINDOW_END` →
  `ACCOUNT_WINDOW_START = 2023-07-02`. Used for `shop.sellers.created_at`
  and `shop.users.created_at` (accounts predate the "recent" product/order
  window — a plausible marketplace shape, though no cross-table invariant
  enforces e.g. "a product's created_at >= its seller's created_at"; this
  is a known simplification, not a bug, since no committed ground-truth key
  or listed task depends on that ordering).
- Verified live at SCALE=1.0: `shop.products.created_at` spans
  `2024-12-30 05:01:04+00 .. 2026-06-30 12:30:03+00` — matches the declared
  window exactly (min near `WINDOW_START`, max at `WINDOW_END`).

### Committed ground truth (`data/ground-truth.json`, SCALE=1.0)

```
seed = 121212, scale = 1.0
row_counts = {sellers: 2000, categories: 60, products: 200000,
              users: 20000, orders: 500000, order_items: 1188048}
products_price_sum = 25876675.79
orders_total_sum = 307483851.66
order_items_qty_sum = 2092188
products_id_checksum = 20000100000   # sum(1..200000) == n*(n+1)/2, since ids are the contiguous 1..n range we assign ourselves
per_category_product_count = {"1".."8": 0 (roots), "9".."60": leaf counts,
                               largest "9" (Headphones & Audio) = 52169}
top_products_by_price = [20 rows of {id, price}, sorted price DESC then id ASC tiebreak,
                          head: {id: 78842, price: 5225.94}, {id: 118914, price: 4837.17}, ...]
```

`products_id_checksum` is deliberately the SUM of all product ids (not a
hash/XOR) — since we assign ids ourselves as the contiguous range
`1..n_products`, the checksum trivially equals `n*(n+1)/2`, but it is still
useful for a validator: a paginated sweep (offset or cursor) that returns
every row exactly once must sum its collected ids to this exact value, AND
return exactly `row_counts.products` rows — either check alone can be
gamed by a buggy pagination (e.g. skip-and-duplicate could coincidentally
sum right), but BOTH together (count AND sum) is what a real validator
should assert.

Money/float fields must be compared with a small tolerance (e.g.
`abs(a - b) < 0.01`) in validators, never exact-decimal equality, per
repo-wide convention.

**sha256 of `data/ground-truth.json`** (SCALE=1.0, as committed):
`d96d3ab6a69c499bd2515a7aaa2d666f58a5d5f18a580e3ae3e110ea4eaba305` — verified
identical across two independent full `generate.py` runs (see
notes-infra.md). If this hash ever changes, either the corpus was
intentionally regenerated (update every consumer) or something drifted
unintentionally (investigate before trusting any downstream validator).

## `shop` schema DDL (clean, properly-indexed — see generate.py's SCHEMA_SQL)

```sql
shop.sellers      (id INTEGER PK, name, tier, rating NUMERIC(3,2), created_at TIMESTAMPTZ)
shop.categories   (id INTEGER PK, parent_id -> categories.id, name, family, depth SMALLINT)
                  + idx on (parent_id)
shop.products     (id BIGINT PK, seller_id -> sellers.id, category_id -> categories.id,
                   title, price NUMERIC(12,2), in_stock BOOLEAN,
                   attrs JSONB NOT NULL DEFAULT '{}', created_at, updated_at TIMESTAMPTZ)
                  + idx on (seller_id), (category_id, id), (created_at, id), GIN(attrs)
shop.users        (id INTEGER PK, email UNIQUE, full_name, country,
                   password_hash TEXT, created_at TIMESTAMPTZ)
shop.orders       (id BIGINT PK, user_id -> users.id, status TEXT,
                   total_amount NUMERIC(12,2), created_at TIMESTAMPTZ)
                  + idx on (user_id, created_at)
shop.order_items  (id BIGINT PK, order_id -> orders.id, product_id -> products.id,
                   qty SMALLINT, unit_price NUMERIC(12,2))
                  + idx on (order_id)
```

Real FKs and PKs everywhere (unlike module 02's cast-across-types
`orders.user_id BIGINT` vs `users.id INTEGER` defect). `status` and `tier`
are plain `TEXT`, not a cramped `VARCHAR(10)` — module 02's defect (h) is
deliberately NOT repeated here. No `NUMERIC(30,10)` overkill on money either
— `NUMERIC(12,2)` throughout, matching real currency precision. Every index
a competent DBA would add for the query patterns this domain implies
(category browse + id-ordered pagination, created_at-ordered
cursor pagination, per-user order history, order → order_items joins, jsonb
attribute filtering) is present; nothing beyond that — no redundant/unused
indexes (module 02's defect (e) is deliberately NOT repeated).

## Verification philosophy per task type

- **Correctness/structural (most tasks)**: the validator computes its own
  oracle either by querying `shop` directly with independent SQL, or via
  the pure `build_*` functions in-memory — NEVER by trusting the learner's
  app's own output as ground truth. E.g. a pagination task's validator
  computes the true `products_id_checksum`/count from `shop.products`
  directly (or from `load_ground_truth()`) and compares against what a full
  paginated sweep of the learner's API actually returned.
- **Timing is NEVER absolute.** Any RPS/latency claim
  (caching speedup, rate-limiter throughput, streaming vs materialize-then-
  serve) goes through `baseline.py` + `write_baseline`/`read_baseline` and
  asserts a RELATIVE improvement on THIS machine, never a hardcoded number.
- **Memory is bounded via `measure_peak_memory`'s tracemalloc PEAK, as a
  RATIO** against a naive/unbounded run (task 05 streaming: peak memory
  serving a large export must stay near-flat as export size grows, unlike
  a naive "materialize the whole result then serialize" implementation)
  — never an absolute byte count.
- **Security tasks (06 SQLi, 07 JWT, 08 secrets)**: an exploit script must
  SUCCEED against the vulnerable stock endpoint (proving the vulnerability
  is real, not theoretical) and FAIL after the fix (proving the fix
  actually closes it) — both directions checked, not just "the fix looks
  right".
- **Load test / bottleneck hunt (09) and the capstone**: `harness/load.py`'s
  `bombard()` against a REAL running app (`run_app_subprocess` for 09,
  since in-process coroutine hand-off would hide the very OS-level
  bottleneck the task is about finding).
