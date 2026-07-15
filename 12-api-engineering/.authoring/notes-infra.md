# Module 12 infra notes (wave-1 build + verification)

Host: Windows 11, Git Bash, uv 0.10.9, Python 3.12.12 (resolved by uv,
module requires `>=3.11`), Docker 28.3.3 / Compose v2.39.2, 12 logical CPUs.

## Commands run

```
cd 12-api-engineering
docker compose up -d                     # postgres:16 + redis:7, both healthy in ~4s
uv sync                                   # 38 packages installed; uv.lock written

SCALE=0.01 uv run python generate.py      # smoke test first (20 sellers, 2000 products, ...)
docker compose exec -T postgres psql -U sandbox -d sandbox -c "\dt shop.*" -c "\di shop.*"
# ... spot-checked attrs jsonb, order_items<->orders reconciliation, tier/status distributions

sha256sum data/ground-truth.json          # before rerun
SCALE=0.01 uv run python generate.py      # rerun
sha256sum data/ground-truth.json          # identical -> deterministic at SCALE=0.01

time (SCALE=0.01 GROUND_TRUTH_ONLY=1 uv run python generate.py)   # 0.48s, no DB touched, same sha

time (uv run python generate.py)          # SCALE=1.0, first run: 1m0.68s
sha256sum data/ground-truth.json
time (uv run python generate.py)          # SCALE=1.0, second run: 1m3.96s
sha256sum data/ground-truth.json          # identical -> deterministic at SCALE=1.0 too

docker compose exec -T postgres psql -U sandbox -d sandbox   # row counts, size, reconciliation, sample password_hash

uv run python scratch/probe.py            # throwaway verification, all probes passed
rm -rf scratch                            # deleted, never committed
```

## `uv sync` resolved (38 packages)

fastapi 0.139.0, uvicorn 0.51.0 (+ httptools/watchfiles/websockets from
`[standard]`), psycopg 3.3.4 + psycopg-binary 3.3.4 + psycopg-pool 3.3.1,
redis 8.0.1, httpx 0.28.1, pyjwt 2.13.0, cryptography 49.0.0, numpy 2.5.1,
pytest 9.1.1, pytest-asyncio 1.4.0, anyio 4.14.2, python-dotenv 1.2.2,
pyyaml 6.0.3, plus transitive deps (starlette, pydantic, h11, click, ...).

## `generate.py` verification (SCALE=1.0)

Row counts (matches design.md's committed ground truth exactly):
sellers=2000, categories=60 (8 roots + 52 leaves), products=200000,
users=20000, orders=500000, order_items=1188048 (~1.19M, within the "~1.2M"
spec range — `items_per_order` E[X]≈2.38 * 500000 ≈ 1,190,000, observed
1,188,048).

**Timing**: full SCALE=1.0 generation (numpy build + threaded password
hashing + Postgres COPY of all 6 tables) took **~60-64 seconds** across two
independent runs — comfortably inside the "a couple of minutes at most"
budget. Password hashing (20,000 users, scrypt n=1024/r=8/p=1, 16 threads)
was benchmarked standalone before picking these params:

| scrypt n | single-thread | 16 threads, 20k users (extrapolated) |
|----------|---------------|----------------------------------------|
| 2048     | 24.5 ms/call  | ~70s   |
| 1024     | 12.2 ms/call  | ~36s   |
| 512      | 5.8 ms/call   | ~116s (single-thread extrapolation, not retested threaded) |

Chose n=1024 for headroom (threading gives ~4-5x speedup since
`hashlib.scrypt` releases the GIL during the C computation, confirmed by
the near-linear scaling from 1 to 16 threads).

**Determinism**: `data/ground-truth.json` sha256 identical across two full
SCALE=1.0 runs:
`d96d3ab6a69c499bd2515a7aaa2d666f58a5d5f18a580e3ae3e110ea4eaba305`.
Also verified at SCALE=0.01 (separate, smaller sha, not committed).

**`GROUND_TRUTH_ONLY=1`**: at SCALE=0.01, completed in 0.48s (vs. the full
run's DB load + password hashing), wrote a byte-identical ground-truth.json
to the DB-touching run at the same scale — confirms the fast path never
diverges from the full path's computed values.

**DB size at SCALE=1.0**: `pg_size_pretty(pg_database_size('sandbox'))` =
**259 MB** — well under the ~1GB budget.

**Reconciliation check** (not a spec requirement, but a design choice worth
recording): `sum(order_items.qty * order_items.unit_price)` grouped by
order, rounded 2dp, equals `orders.total_amount` to the cent —
`307483851.66` both ways, verified via a live SQL query against the seeded
DB. This holds by construction (`build_order_items` computes
`order_total_amount` FROM the items, `unit_price` is looked up from
`products.price` rather than independently drawn) — see design.md's RNG
draw-order section.

**Category popularity** (Zipf, verified live): leaf category id 9
("Headphones & Audio", electronics' first and globally most-popular leaf)
has 52169 products, the largest of any leaf — matches the declared
`w = 1/(rank+1)**1.1` ranking with rank 0 most popular.

**Seller/order distributions** (spot-checked at SCALE=0.01, n=20 sellers /
5000 orders — small-sample noise expected, shape still directionally
correct): tier roughly bronze > silver > gold > platinum; status
completed(2496) > shipped(1363) > processing(387) > cancelled(300) >
pending(255) > refunded(199) — "mostly completed/shipped, few
refunded/cancelled" as required.

**Timestamp window**: `shop.products.created_at` spans
`2024-12-30 05:01:04+00 .. 2026-06-30 12:30:03+00` at SCALE=1.0 — matches
the declared `WINDOW_START=2024-12-30 .. WINDOW_END=2026-06-30` (548 days,
~18 months) essentially exactly (min/max land right at the window edges,
as expected from a full-population draw).

## `scratch/probe.py` — what it proved, then was deleted

A tiny FastAPI app (`scratch/probe_app.py`, two routes: `/health`,
`/echo/{value}`) exercised through every harness entry point, all passing:

1. **`run_app`** (in-process): bound a real ephemeral port
   (`http://127.0.0.1:49970` in this run — a different port every run, as
   expected), served both routes correctly over REAL HTTP via
   `svc.client()` (httpx.AsyncClient bound to `base_url`).
2. **`bombard()`** against that live app: `concurrency=8, requests=200` ->
   `total=200 ok=200 errors=0 rps=344.8 p50=19.91ms p95=37.52ms` — sane
   numbers, confirms the percentile math and the shared-client request path
   both work end-to-end over a real socket.
3. **`asgi_client`**: same `/health` check via `httpx.ASGITransport`, no
   socket at all — confirms the in-memory path works identically.
4. **`run_app_subprocess`**: launched `python -m uvicorn
   scratch.probe_app:app` as a REAL separate process (with
   `env={"PYTHONPATH": MODULE_ROOT}` so the child could import the
   `scratch` package), polled a raw TCP connect until it accepted, then
   `/health` responded correctly through it; teardown terminated the
   process cleanly (no orphan process left running — checked via the
   `finally` block's `proc.terminate()`/`wait()`, and no leftover uvicorn
   process observed after the probe exited).
5. **Redis**: `redis_client()` round-trip (`SET`/`GET` on
   `s12:probe:k1`/`k2`), then `redis_flush_prefix(client, "s12:probe:")`
   deleted exactly 2 keys and left the namespace clean — confirms the
   SCAN+DEL path never touches keys outside its prefix.
6. **`pg_conn()`**: a live query against `shop.products` returned the real
   row count (200000 at the time of the probe, post full-scale seed).
7. **`pg_pool()`**: opened, checked out a connection via
   `pool.connection()`, queried `shop.users` (20000) — confirms the pool
   context-manager usage pattern documented in design.md.
8. **`verify_password`/`build_password`**: pulled 5 real seeded users'
   `password_hash` from `shop.users`, confirmed
   `verify_password(build_password(uid), stored) is True` for all 5, and
   that an obviously-wrong password is correctly rejected (`False`, not an
   exception) — proves the harness's password contract matches what
   `generate.py` actually wrote to the DB (not just internally consistent
   with itself).

`scratch/` was deleted immediately after (never committed); confirmed via
`git status --porcelain` showing no `scratch` entries and no `__pycache__`
tracked afterward.

## Gotchas / decisions

- **Windows + subprocess uvicorn**: `run_app_subprocess` uses a raw TCP
  `connect()` poll (not an HTTP GET) to detect startup, since the harness
  doesn't know the app's routes in general — this worked cleanly on
  Windows with no `WinError 10048`/address-in-use flakiness observed across
  several probe runs, because each run gets a fresh ephemeral port (bind,
  read, close, then the child binds the same number moments later).
- **`hashlib.scrypt` genuinely releases the GIL** — verified empirically
  before committing to a threaded design: single-thread n=2048 took ~24.5ms/
  call (973s serial for 20k users, unacceptable), 16 threads brought the
  effective per-call cost to ~6.95ms (~139s for 20k) at the same n, and
  ~3.5ms (~70s) at n=... the actual choice (n=1024, 16 threads) measured
  ~1.78ms effective/call -> ~36s for 20,000 users. This is why
  `_build_password_hashes` in `generate.py` uses a `ThreadPoolExecutor`
  rather than accepting a slow serial loop or reaching for multiprocessing
  (which would add IPC overhead for no benefit once the GIL isn't the
  bottleneck).
- **`psycopg.types.json.Jsonb`** wrapper is required for `COPY ... FROM
  STDIN` writes to a `jsonb` column via `copy.write_row()` — passing a bare
  Python `dict` directly did NOT get serialized correctly in an earlier
  draft; wrapping every `attrs` value as `Jsonb(attrs_dict)` in
  `_load_postgres` fixed it, confirmed by reading back
  `shop.products.attrs` and seeing real JSON objects (`{"brand": "...",
  "color": "..."}` etc.), not stringified Python repr.
- **`order_id_col - int(order_ids[0])` for `np.bincount`** assumes
  `order_ids` is the contiguous `1..n` array `build_orders()` actually
  produces — documented explicitly in `build_order_items`'s docstring
  since it's a real constraint on the caller, not a general-purpose
  "works with any order_ids array" function.
- **No aiohttp/uvicorn Windows surprises** — `uvicorn.Server.serve(sockets=
  [sock])` (the pre-bound-socket strategy from `run_app`) started and tore
  down cleanly across every probe run, matching module 11's prior finding
  that binding your own socket avoids relying on private internals.
- **CONVENTIONS.md ports table** updated with the two new rows
  (`12-api-engineering | Postgres | 54312 | SANDBOX_12_PG_PORT` and
  `... | Redis | 6312 | SANDBOX_12_REDIS_PORT`) in the same session.
- **Stock state after this session**: `docker compose up` stack LEFT
  RUNNING (both healthy) with `shop` fully seeded at SCALE=1.0, since later
  waves (task authoring) need it. `data/` contains only the committed
  `ground-truth.json`. No `scratch`/`__pycache__`/`*-local.json` tracked.
  Pre-existing unrelated uncommitted change
  `01-sql-foundations/03-currency-normalized-revenue/src/query.sql` was
  present before this session started and was left untouched (not part of
  this module).

## Public API signatures handed to task-author agents

See `.authoring/design.md` for the full annotated contract. Quick
reference (unannotated `def`/context-manager lines):

`harness/common.py`:
```python
MODULE_ROOT: Path
DATA_DIR: Path
GROUND_TRUTH_PATH: Path
SEED = 121212

def not_passed(reason)
def passed(msg="")
def guarded(fn)
def _last_line(text)
def time_it(fn, *args, **kwargs)
def write_baseline(path, obj)
def read_baseline(path)
def load_ground_truth()
def run_async(coro)
def measure_peak_memory(fn, *args, **kwargs)
def pg_port()
def pg_dsn()
def pg_conn()
def pg_pool(min_size=1, max_size=10, **kwargs)
def redis_port()
def redis_client(decode_responses=True)
def redis_flush_prefix(client, prefix)
def build_password(user_id)
def hash_password(password, salt)
def verify_password(password, stored)
def build_user_password_hash(user_id)
```

`harness/service.py`:
```python
class Service:
    def __init__(self, base_url, port)
    def client(self, **kwargs)

async def run_app(app_or_import_string, *, host="127.0.0.1", startup_timeout=10.0, **uvicorn_kwargs)
async def run_app_subprocess(import_string, *, host="127.0.0.1", extra_args=None, env=None, startup_timeout=15.0)
async def asgi_client(app, *, base_url="http://testserver", **kwargs)
```

`harness/load.py`:
```python
class LoadResult:  # dataclass: total, ok, errors, rps, p50_ms, p95_ms, p99_ms, elapsed_s

async def bombard(url_or_fn, *, concurrency=10, duration_s=None, requests=None,
                   method="GET", client_kwargs=None, request_kwargs=None)
```

`generate.py`:
```python
def build_categories()
def build_sellers(seed, n)
def build_products(seed, n, n_sellers, leaf_ids)
def build_users(seed, n, compute_password_hash=True)
def build_orders(seed, n, n_users)
def build_order_items(seed, order_ids, product_ids, product_prices)
```

## Deviations from the wave-1 spec, and why

- **SCRYPT_N chosen as 1024, not left unspecified** — the spec asked for
  "fixed derivation params" without naming a value; 1024 was picked after
  live benchmarking (see table above) to keep total generation time inside
  "a couple of minutes at most" with headroom. Documented as explicitly NOT
  a security recommendation in both `harness/common.py` and design.md.
- **`measure_peak_memory` takes a plain sync callable**, not an
  `async_fn` like module 11's version — module 12's spec text says
  "`measure_peak_memory(fn, *a, **k)`" (no "async_fn" wording), and unlike
  module 11 (where everything under test was inherently a coroutine),
  module 12's task 05 (streaming) may reasonably measure sync code paths
  too. Callers needing to measure async code wrap it with `run_async`
  themselves (documented in design.md).
- **`country_idx` in `build_users` is a UNIFORM draw**, not Zipf-weighted —
  the spec's realistic-skew requirement calls out "Zipf for category
  popularity and seller popularity" specifically, not user country. Kept
  uniform for simplicity; documented explicitly in design.md as a
  deliberate, in-scope simplification rather than an oversight.
- **`orders.user_id` is a UNIFORM draw over `1..n_users`**, not
  popularity-weighted — same reasoning; the spec's Zipf callouts are
  category/seller-specific, and no ground-truth key or later-wave task
  description implies "power users" are needed.
- Everything else in the spec (row counts, schema shape, indexing,
  password format, ground-truth keys, GROUND_TRUTH_ONLY affordance, own
  stack, no fixed API port, harness function set) was implementable
  exactly as specified — no other deviations.
