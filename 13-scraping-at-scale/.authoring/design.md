# Module 13 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents every
decision behind the hostile target site, the harness API, the corpus RNG
draw order, the committed ground-truth values, and the verification
philosophy per task type. This is the shared contract for every agent
working on this module (infra, generator, task authors, validators). If you
change something here, regenerate, reverify live, and update every
consumer in the same change.

This is the WAVE-1 infrastructure build: docker-compose, pyproject/uv.lock,
generate.py, harness/, and the target site itself (docker/target/). No task
directories exist yet (01-07 + capstone + optional k8s-bonus are authored in
a later wave against this infra).

**`data/catalog.json` and `data/target-spec.json` are NOT reference
solutions**, but they are not meant for a learner to read directly either —
they are the target app's OWN backend data (a real site's product DB and
WAF config aren't handed to whoever's scraping it). Reading
`target-spec.json` trivially reveals rate-limit thresholds, honeypot ids,
markup-version assignment, and bad-record ids, which would gut tasks 01
(recon) and 04 (selector resilience). Task READMEs authored in later waves
must say so explicitly, the same way `.authoring/` itself is off-limits.
Only `data/ground-truth.json` is committed and is the module's usual
validator oracle (same convention as every other module).

## Emulation decisions — what is real, what is a deterministic stand-in

- **TLS/JA3 fingerprinting is DELIBERATELY OUT OF SCOPE.** Everything is
  plain HTTP (no TLS termination anywhere in docker-compose). The target's
  "client fingerprint" defense is HEADER/BEHAVIORAL ONLY: it inspects
  `User-Agent` / `Accept-Language` and request timing/pattern (rate limit,
  honeypots). This is a planned SECOND-WAVE module (a follow-on that adds
  real TLS/JA3-shaped detection) — do not attempt to fake it here with,
  e.g., raw-socket TLS ClientHello inspection; that is explicitly not this
  module's curriculum.
- **Headless browser rendering is EMULATED, not real.** There is no
  Playwright/Selenium/real browser anywhere in this module, ever. Some
  product fields (`rating`, `shipping_info`) are "JS-only": absent from the
  server-rendered HTML at `/product/{id}` and only obtainable by calling the
  documented XHR-style endpoint `GET /api/product/{id}`. Fetching that
  endpoint is the deterministic stand-in for "running a headless browser to
  let client-side JS populate the DOM" — and it is modeled as substantially
  MORE EXPENSIVE in the cost model (`api_extra_cost` = 7x the html fetch),
  exactly the tradeoff a real headless-render step would represent.

## Ports

| Service              | Host port | Env var                    |
|-----------------------|-----------|-----------------------------|
| Target site (HTTP)    | 8313      | `SANDBOX_13_TARGET_PORT`   |
| Prometheus            | 9313      | `SANDBOX_13_PROM_PORT`     |
| Grafana               | 3313      | `SANDBOX_13_GRAFANA_PORT`  |

No Postgres in this module. Data-quality sinks (clean/quarantine, task 02)
are files (JSONL/Parquet) under gitignored per-task work dirs — never a
shared database. Task 06's scraper (Prometheus/Grafana observability) runs
on the HOST like module 12's task apps, exposing a `prometheus_client`
`/metrics` endpoint on **port 9113 by convention** (not in the ports table
above since it's a learner dev-server port, not a docker-compose service —
same rationale as module 12's "no fixed API port"); `docker/prometheus/
prometheus.yml`'s `spider` job scrapes `host.docker.internal:9113`.

## Harness API (`harness/common.py`)

Every third-party import (`httpx`) is lazy inside the function that needs
it; importing `harness.common` has zero side effects and requires nothing
running.

```python
MODULE_ROOT: Path                    # 13-scraping-at-scale/
DATA_DIR: Path                       # MODULE_ROOT / "data"
GROUND_TRUTH_PATH: Path              # DATA_DIR / "ground-truth.json"
CATALOG_PATH: Path                   # DATA_DIR / "catalog.json"
TARGET_SPEC_PATH: Path               # DATA_DIR / "target-spec.json"
SEED = 131313

TARGET_DEFAULT_PORT = 8313
PROM_DEFAULT_PORT = 9313
GRAFANA_DEFAULT_PORT = 3313
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"

def not_passed(reason) -> NoReturn
def passed(msg="") -> NoReturn
def guarded(fn) -> Callable
def _last_line(text) -> str

def time_it(fn, *a, **k) -> tuple
def write_baseline(path, obj) -> Path
def read_baseline(path) -> dict | None

def load_ground_truth() -> dict     # NOT PASSED("...run generate.py first") if missing
def load_catalog() -> dict          # NOT PASSED("...run generate.py first") if missing
def load_target_spec() -> dict      # NOT PASSED("...run generate.py first") if missing

def target_port() -> int
def target_base_url() -> str
def prom_port() -> int
def prom_base_url() -> str
def grafana_port() -> int
def grafana_base_url() -> str

class TargetClient:
    def __init__(self, client_id=None, base_url=None, headers=None, **httpx_kwargs)
    def get(self, path, **kwargs)
    def close(self)
    # context-manager: __enter__/__exit__

def get_client_state(client_id, base_url=None) -> dict   # GET /__debug/client, NOT PASSED if unreachable
def reset_client(client_id, base_url=None) -> dict       # POST /__debug/reset, NOT PASSED if unreachable
def query_prometheus(expr, base_url=None) -> dict | None # None if Prometheus down; caller decides skip vs fail
```

Design notes:

- `TargetClient` is deliberately minimal — it exists so validators/harness
  scripts can poke the target without duplicating a scraping stack. It sets
  a browser-like default `User-Agent`/`Accept-Language` (passes the header
  gate) and a per-instance `X-Client-Id` (random `uuid4` unless given). **The
  learner writes their OWN fetch layer for every actual task** — nothing in
  `harness/` does parsing, retries, rate-limit backoff, or honeypot
  avoidance; that is the entire point of the module.
- `query_prometheus` returns `None` on any connection failure rather than
  raising or calling `not_passed` itself — Prometheus/Grafana live checks
  are ALWAYS skip-if-down in this module (see "Verification philosophy"
  below); the caller decides whether that means skip the assertion or fail
  the task.
- No `pg_conn`/`redis_client`-equivalents exist in this module at all —
  there is no shared database. A task needing writable state (quarantine
  sinks, change-detection state, cost-router logs) uses its own gitignored
  work dir under the task folder (`*/run/`, `*/sinks/`), never a shared
  service.

## Target app (`docker/target/app.py`)

FastAPI, single uvicorn worker (`--workers 1`) — per-client state is a
plain in-memory `dict`, correct only because there is exactly one worker
process; it does NOT survive a container restart, by design (a task
touching "does state survive a restart" is out of scope for this module).
Reads `CATALOG_PATH`/`TARGET_SPEC_PATH` (env, default `/data/catalog.json`
/ `/data/target-spec.json`) once at import time.

### Request pipeline (`defense_middleware`, applies to every route NOT under `/__debug/`)

1. **Debug bypass**: `/__debug/*` paths return before ANY of the checks
   below run (no header gate, no rate limiting, no counting) — validators
   can always read/reset client state regardless of what that client has
   tripped.
2. **Ban check**: if the resolved client is already `banned`, every request
   gets `403 {"error": "forbidden", "reason": "banned"}` immediately,
   regardless of headers.
3. **Header gate**: `User-Agent` must CONTAIN `required_headers.
   user_agent_substring` (`"Mozilla/5.0"`) AND (if `accept_language_
   required`, which it is) `Accept-Language` must be present and non-blank.
   Failing either -> `403 {"error": "forbidden", "reason":
   "missing_or_invalid_headers"}`, increments `header_rejections`. This is
   the ENTIRE fingerprint defense (see "Emulation decisions" above) — no
   TLS/JA3 inspection exists anywhere.
4. **Honeypot check**: `/trap/{anything}` (path prefix match, not a token
   allowlist — ANY path under `/trap/` is a trap) OR `/product/{id}` /
   `/api/product/{id}` where `id` is in the honeypot id range ->
   `honeypot_hits += 1`, `banned = True` IMMEDIATELY (no threshold), and a
   200 decoy response (never a 404 — a naive scraper sees what looks like a
   normal missing/unavailable listing, not an obvious trap signal).
5. **Rate limit**: token bucket, `capacity=25`, `refill_per_sec=50.0`,
   refilled lazily on every request (`tokens = min(capacity, tokens +
   elapsed * refill_per_sec)`). A request costs 1 token; if fewer than 1 is
   available -> `429 {"error": "too_many_requests"}` (with `Retry-After:
   1`), `rate_limit_violations += 1`. Once `rate_limit_violations >=
   ban_after_violations` (25, CUMULATIVE count, not a rolling window),
   `banned = True` from then on. Tuned so the **burst/concurrency gate**
   (`capacity`), not the sustained rate, is what catches an abusive
   scraper: a client that PACES its dispatch at or below `refill_per_sec`
   (~50 req/s) never exhausts the bucket and accrues ~0 violations, while a
   client that fires an unbounded burst (e.g. `asyncio.gather` over
   hundreds of ids with no pacing) drains the 25-token bucket in a fraction
   of a second and crosses `ban_after_violations` almost immediately. See
   "Rate-limit retune (post wave-1)" below for the live numbers and the
   Windows-timer gotcha that shaped how a "polite" reference crawler must
   actually pace itself.
6. Otherwise the request proceeds to the actual route; `requests += 1`
   happens on EVERY branch above too (a rejected/banned/rate-limited
   request still counts as a request for `/__debug/client`'s `requests`
   field).

### Rate-limit retune (post wave-1)

The rate limiter shipped in the initial wave-1 build (`capacity=10`,
`refill_per_sec=3.0`, `ban_after_violations=15`) was too aggressive for a
4,000-product catalog: a well-behaved crawler capped at ~3 req/s would need
~22 minutes for one full sweep, impractical for both a learner and any
validator that crawls the whole catalog. Retuned to `capacity=25`,
`refill_per_sec=50.0`, `ban_after_violations=25` — live-verified against
the running target (SCALE=1.0, 4,000 products):

- **Polite crawler** (bounded concurrency=16 + an explicit PACED dispatch
  rate, ~47 req/s, with 429-triggered backoff as a safety net): full
  4,000-product sweep in **85.10s**, `200` on every request,
  `rate_limit_violations=0`, `banned=false`.
- **Naive crawler** (`asyncio.gather` over 300 ids with ZERO pacing —
  everything fired at once): **2.33s** elapsed, `rate_limit_violations=25`
  (crossed `ban_after_violations` almost immediately), `banned=true`,
  247/300 of the remaining requests in that same burst already getting
  403'd.

**Important gotcha for whoever writes task 01's reference/validator
crawler**: on this target, request handling is sub-millisecond (in-memory
dict lookups, no I/O) — **bounded concurrency ALONE does not cap
throughput** the way it would against a real, slower site. A semaphore of
8-16 with no other pacing measured ~220 req/s in testing (nearly 4.5x the
50 req/s refill ceiling) and got banned almost instantly. A genuinely
"polite" client on THIS target needs an EXPLICIT dispatch-rate pacer (not
just a concurrency cap) to stay under `refill_per_sec`. A naive fixed
`await asyncio.sleep(interval)` between dispatches also has a subtlety on
Windows: the default event-loop timer resolution (~15.6ms) quantizes any
short requested sleep to multiples of that tick, so requesting, e.g., a
58 req/s pace can silently deliver the SAME actual rate as a 45 req/s
request (both round to a 2-tick, ~32 req/s pace) — a naive drift-
compensating scheduler (`next_dispatch += interval` without capping
catch-up) is worse: it lets the event loop "catch up" with a burst of
several dispatches back-to-back after any scheduling lag, which is exactly
the kind of transient spike that exhausts a 25-token bucket even though
the AVERAGE rate looks fine. The reference pacer used for this
verification instead accumulates fractional "tokens" from REAL measured
wall-clock elapsed time each wake (self-calibrating, platform-independent)
rather than trusting any single `sleep()` call's requested duration — see
`.authoring/notes-infra.md`'s "Rate-limit retune verification" for the
runnable pattern. Task 01's hints/validator should point at pacing-by-
measured-elapsed-time (or an equivalent real token-bucket client), not
"just add a semaphore," if they want a learner's polite-crawler check to
be meaningful on this target.

### Client identity resolution (`_client_key`)

`X-Client-Id` header if present, else a fallback `f"anon-{host}:{port}"`
derived from the request's TCP peer address (`request.client`). Because
`httpx`/most HTTP clients reuse a connection (and therefore a source port)
across many requests, a scraper that never sets `X-Client-Id` still gets
SOME consistent rate-limit bucket per open connection — but a new
connection (new source port) resets it, which is itself a realistic
"anonymous client" behavior worth a task noticing.

### Routes

- `GET /` — landing page (product count + a link to `/catalog`).
- `GET /robots.txt` — `Disallow: /trap/` and `Disallow: /__debug/`. Real
  crawlers respect this; a naive "follow every `<a href>`" crawler that
  ignores robots.txt walks straight into `/trap/*` anyway (a deliberate
  task-01 teaching moment: robots.txt tells you exactly where the traps are
  and a naive crawler still gets banned).
- `GET /catalog?page=&day=&v=&chaos=` — paginated real-product listing
  (`PAGE_SIZE=50`, id-ordered), PLUS `HONEYPOTS_PER_PAGE=2` hidden honeypot
  `<a style="display:none" rel="nofollow" class="hp">` links per page
  (round-robin through the honeypot id pool, deterministic per page number)
  and, on page 1 only, one hidden `/trap/{token}` link. `v`/`chaos` are
  forwarded into each product link's query string so a listing crawl and a
  detail crawl can agree on markup version.
- `GET /product/{id}?day=&v=&chaos=` — HTML detail page. 404 for an id that
  is neither a real product nor a honeypot (honeypot ids never reach the
  route handler — the middleware already returned a decoy). Renders via one
  of 4 markup versions (see below), with day-overlay and bad-record defects
  applied first, and a fresh per-request `x-nonce`.
- `GET /api/product/{id}?day=` — JSON: the full clean-or-defective record
  (day-overlay + defect applied, same as the HTML path) PLUS `rating` and a
  nested `shipping_info: {free, eta_days, carrier}` — the two JS-only
  fields, never present in ANY html version. Also carries a fresh `_nonce`.
- `POST` is not needed anywhere except the debug endpoints below.
- `GET /__debug/client` (reads `X-Client-Id`, 400 if absent) -> `{client_id,
  requests, honeypot_hits, rate_limit_violations, header_rejections,
  banned}`. An id never seen before returns all-zero/`banned=false` (not an
  error) — a validator can query before any prior traffic.
- `POST /__debug/reset` (reads `X-Client-Id`, 400 if absent) -> re-inits
  that client's state to fresh (`{"client_id", "reset": true}`).

### Markup versions (`build_markup_versions`, K=4)

Default assignment (no `?v=`, chaos disabled) is a FIXED per-product
formula: `version = 1 + (product_id % 4)` — deterministic, no rng, no day
dependency. This means the SAME crawl encounters all 4 encodings across
different products (not across time), which is what makes task 04's
fallback-chain requirement real: you cannot special-case "today's
template", you have to handle all 4 unconditionally.

1. **`classic-div`** — plain `<div>`/`<span>` structure with descriptive
   class names (`.product-title`, `.price-block .price`, `.stock`,
   `.reviews`, `.description`). Price is visible text `"CURRENCY AMOUNT"`.
2. **`microdata`** — `schema.org/Product` `itemprop` microdata. Price is
   BOTH a `<meta itemprop="price" content="...">` (machine-readable) AND a
   separate visible `.display-price` span in a DIFFERENT field order
   (`"AMOUNT CURRENCY"`, amount first) — a deliberate trap for a selector
   that assumes the two must agree in format.
3. **`jsonld`** — price/currency/availability exist ONLY inside a
   `<script type="application/ld+json">` `schema.org/Product` block; there
   is NO visible price text anywhere else on the page. A selector chain
   that only looks for `.price`-shaped CSS will silently fail on this
   version.
4. **`data-island`** — minimal semantic HTML shell (title/brand/category/
   review-count/description only); `price`/`currency`/`in_stock`/`seller`
   live ONLY inside `<script id="__DATA__" type="application/json">`,
   mimicking a client-side-rendered SPA shell that happened to leave its
   hydration payload in the initial HTML.

`?v=1..4` always wins (explicit override, used by validators to exercise
every branch deterministically). Absent `v`: chaos mode (`?chaos=1` query
OR `TARGET_CHAOS=1` env) cycles version by wall-clock (`1 + (floor(time() /
30) % 4)`, `CHAOS_PERIOD_SEC=30`) instead of the steady per-product default
— reserved for the capstone's "the site changed shape mid-crawl" drill.
`v` still overrides chaos too.

### Honeypots (`build_honeypots`)

`honeypot_ids` = a CONTIGUOUS block immediately above the real product id
range: `[n_products+1, n_products+honeypot_count]` (30 at SCALE=1.0) — a
validator/the app itself classifies "is this id a honeypot" with one range
check, no lookup table needed. `trap_tokens` = 5 random 8-hex-digit slugs
for the separate `/trap/{token}` vector (matched by PATH PREFIX in the
middleware, not an allowlist — any token under `/trap/` traps, including
ones a learner's own exploratory curl might invent). Both vectors are ONLY
reachable via hidden markup (`display:none` / `class="hp"` / `rel=
"nofollow"`) in `/catalog` listings — never linked from a real product page,
and `robots.txt` explicitly disallows `/trap/`.

### Bad records (`build_bad_records`, ~10% of products, 6 defect types)

`BAD_FRACTION = 0.10`, deterministically chosen (no replacement) and split
as evenly as possible across the 6 types. Applied identically to BOTH the
HTML detail page and the `/api/product/{id}` JSON (defects are a property
of the record, independent of which endpoint or markup version served it):

| defect            | effect                                                          |
|--------------------|------------------------------------------------------------------|
| `missing_price`    | `price` key entirely ABSENT (html: empty price text; json: no `price` key at all) |
| `price_na`         | `price` is the literal string `"N/A"`                            |
| `empty_title`      | `title` is `""`                                                  |
| `negative_price`   | `price` is a negative number                                     |
| `bad_currency`     | `currency` is `"XYZ"` (unknown ISO code)                         |
| `truncated`        | `description` cut to ~1/3 length plus a `"...[TRNC]"` + mojibake suffix |

### Per-day changes (`build_change_days`, N_DAYS=5, days 0..4)

Day 0 is the baseline (no overlay). Each day 1..4 is drawn with ITS OWN
seed (`SEED_CHANGES + day`) so a validator can recompute a single day's
change set without replaying earlier days, but the recorded new values are
CUMULATIVE — `generate.py` walks days 1..4 in order, maintaining running
`price`/`in_stock` arrays, so day D's recorded value is relative to day
D-1's EFFECTIVE state, not always the original baseline.
`CHANGE_FRACTION=0.04` (~4% of products) per day; 70% of a day's chosen ids
get a price change (`new = round(current * uniform(0.85, 1.20), 2)`), 30%
get an `in_stock` flip. The app folds these into a `_CUMULATIVE_OVERLAY`
dict ONCE at startup (`{day: {product_id: {"price": x} | {"in_stock": b}}}`
per day, each already merged with all earlier days) so serving `?day=D`
costs one dict lookup per product, not a D-step replay per request.

### Volatile nonce (the noise a fingerprint must exclude)

Every HTML response embeds `<meta name="x-nonce" content="{uuid4}">`
(classic-div/microdata; a `<!-- nonce:... -->` comment on microdata, a
hidden `<span class="hidden-nonce" style="display:none">` on jsonld, and
folded into the `__DATA__` json island's `"nonce"` key on data-island —
each markup version encodes it DIFFERENTLY, same as every other field);
every JSON response (`/api/product/{id}`, and both decoy responses) carries
a top-level `"_nonce"` key. It is a fresh random `uuid4` on literally every
request, unrelated to `day`/`v`/product id. Two requests for the SAME
`?day=` of an UNCHANGED product are byte-identical except this one field —
task 03's fingerprint (whatever hash/diff scheme the learner builds) must
explicitly strip it before comparing, or every page will look "changed"
every single request.

### Cost model (task 05's budget router)

```
http_cost       = 1.0   # GET /product/{id} — cheap
api_extra_cost  = 7.0   # the ADDITIONAL cost of also calling GET /api/product/{id}
render_cost     = 8.0   # http_cost + api_extra_cost — "full render" of one product
completeness_target = 0.98
```

A product's `rating`/`shipping_info` are ALWAYS absent from HTML (every
product, every markup version) but only count as REQUIRED for that
product's completeness score when `review_count > 0` — and `review_count`
ITSELF is HTML-visible (rendered in every markup version as `.reviews` /
`.rv` text). This is what makes the router's decision non-trivial and
non-vacuous: a router can look at the html-fetched record's `review_count`
and decide "no reviews yet -> nothing js-only is actually missing -> don't
bother rendering" without ever calling the api. `review_count ~
Poisson(0.357)` is tuned so `P(review_count > 0) ≈ 30%` (verified at
SCALE=1.0: `requires_detail_fraction = 0.2978`, inside the target 25-35%
band).

At SCALE=1.0 (`n_products=4000`, verified live via `generate.py`'s printed
`cost_model`):

| strategy    | completeness | cost      | notes                                    |
|-------------|--------------|-----------|--------------------------------------------|
| all-HTTP    | 0.7023       | 4,000     | FAILS the 0.98 target — every product with reviews is missing rating/shipping_info |
| all-render  | 1.0          | 32,000    | meets target, 8x the cost of all-HTTP     |
| mixed       | 1.0          | 12,337    | meets target at **2.59x cheaper than all-render** (escalates to `/api/product/{id}` only for the ~29.78% of products with `review_count > 0`) |

`mixed_cost = n_products * http_cost + requires_detail_count *
api_extra_cost = 4000*1.0 + 1191*7.0 = 12337.0`, exactly reproducing
`all_render_cost / mixed_cost ≈ 2.594`.

## Catalog schema (`data/catalog.json`)

```
seed, scale, n_products, n_sellers
categories: [{id, name}]            # 10 fixed: electronics, home-goods, books,
                                     # toys, sporting-goods, office-supplies,
                                     # beauty, apparel, grocery, automotive
sellers:    [{id, name}]            # Zipf-popularity assigned in build_products
products:   [{
  id, slug, url, title, category, brand,
  price, currency, in_stock,
  seller_id, seller_name,
  review_count,                     # HTML-visible; drives requires_detail
  rating,                           # JS-ONLY -- null if review_count == 0
  shipping_free, shipping_eta_days, shipping_carrier,  # flattened here;
                                     # nested as shipping_info={free,eta_days,
                                     # carrier} in the /api/product/{id} JSON
  description,
}]
```

`js_only_fields = ["rating", "shipping_info"]` — exactly these two
top-level names in every ground-truth/target-spec reference; `shipping_info`
is the NESTED name the API actually returns (the catalog stores its three
components flat purely as a generation-time convenience).

## RNG draw order (`generate.py`, do not reorder without regenerating)

```python
SEED = 131313                  # harness.common.SEED
SEED_SELLERS     = SEED + 1
SEED_PRODUCTS    = SEED + 2
SEED_BAD_RECORDS = SEED + 3
SEED_HONEYPOTS   = SEED + 4
SEED_CHANGES     = SEED + 5    # + day (1..4) for build_change_days' per-day rng
```

- **`build_categories()`** — pure, NO rng: 10 fixed categories, ids 1..10 in
  `CATEGORIES` declaration order.
- **`build_sellers(seed, n)`** — SE1 word-1 index, SE2 word-2 index (both
  uniform, for `name`).
- **`build_products(seed, n, n_sellers, seller_names, categories)`** —
  P1..P14, P14 inside a fixed per-category loop (mirrors module 12's
  per-family title loop):
  `P1` category via Zipf (`rank` = position in `CATEGORIES`, `w =
  1/(rank+1)**1.1` — electronics is rank 0, the most popular, confirmed live
  at SCALE=1.0: 1,492 of 4,000 products, by far the largest category), `P2`
  a seller-popularity PERMUTATION (`rng.permutation(n_sellers)+1`, `w =
  1/rank**1.2`), `P3` `seller_id` (Zipf-weighted choice using P2's
  weights), `P4` standard-normal `z` for the log-normal price (median/sigma
  per category from `CATEGORY_PRICE_PROFILE`, clipped `>= 0.5`, rounded
  2dp), `P5` `currency` (`p=[.90,.05,.03,.02]` over USD/EUR/GBP/CAD), `P6`
  `in_stock` (`p=0.85`), `P7` `review_count` (`Poisson(0.357)`), `P8`
  standard-normal `z` for `rating` (`clip(4.3 + 0.5*z, 1.0, 5.0)`, rounded
  1dp, set to `null` wherever `review_count == 0`), `P9` `shipping_free`
  (`p=0.60`), `P10` `shipping_eta_days` (weighted choice over `[1,2,3,5,7,
  10]`), `P11` `shipping_carrier` (uniform over 4 carriers), `P12` `brand`
  index (uniform over 20), `P13` title-adjective index (uniform over 10),
  P14 — inside the per-category loop — a noun index sized to that
  category's matched-row count, combined with P13's adjective for `title`.
  `slug`/`url`/`description` are assembled afterward in a plain Python loop
  (no further rng consumption).
- **`build_bad_records(seed, product_ids, fraction, defect_types)`** —
  one `rng.choice(..., replace=False)` for the affected id subset, one
  `rng.shuffle` before splitting evenly across the 6 defect types in
  `DEFECT_TYPES` order.
- **`build_honeypots(seed, n_products, count, n_trap_tokens)`** — honeypot
  PRODUCT ids are a plain contiguous range (no rng); `trap_tokens` are the
  only rng draw here (`rng.integers(0, 16, size=(n_trap_tokens, 8))` mapped
  to hex digits).
- **`build_change_days(seed, product_ids, baseline_price,
  baseline_in_stock, n_days, fraction)`** — walks days 1..n_days-1 in
  order, EACH day using its own `default_rng(seed + day)`: `rng.choice`
  for that day's changed-id subset, `rng.random` for the price-vs-stock
  coin flip (`p=0.70` price), `rng.uniform(0.85, 1.20)` for the price
  factor — applied to the RUNNING (cumulative) price/stock arrays, not the
  original baseline.
- **`build_cost_model(n_products, review_count, ...)`** — pure, NO rng
  (aggregates already-drawn `review_count`).

## Committed ground truth (`data/ground-truth.json`, SCALE=1.0)

```
seed = 131313, scale = 1.0, n_products = 4000
price_sum = 276723.8
per_category_counts = {electronics: 1492, home-goods: 694, books: 450,
                        toys: 334, sporting-goods: 242, office-supplies: 204,
                        beauty: 188, apparel: 159, grocery: 126, automotive: 111}
js_only_fields = ["rating", "shipping_info"]
honeypot_ids = [4001..4030]  (30 ids)
trap_tokens = [5 hex-8 tokens]
bad_records.total = 400
bad_records.by_defect counts = {missing_price: 67, price_na: 67, empty_title: 67,
                                 negative_price: 67, bad_currency: 66, truncated: 66}
markup_version_count = 4
change_days = {"1": [160 ids], "2": [160 ids], "3": [160 ids], "4": [160 ids]}
cost_model = {http_cost: 1.0, api_extra_cost: 7.0, render_cost: 8.0,
              completeness_target: 0.98,
              requires_detail_count: 1191, requires_detail_fraction: 0.2978,
              all_http_completeness: 0.7023, all_render_completeness: 1.0,
              mixed_completeness: 1.0,
              all_http_cost: 4000.0, all_render_cost: 32000.0, mixed_cost: 12337.0}
```

Money fields (`price_sum`, any per-product price) must be compared with a
small tolerance (e.g. `abs(a - b) < 0.01`) in validators, never exact
equality, per repo-wide convention.

**sha256 of `data/ground-truth.json`** (SCALE=1.0, as committed):
`335e94cae56e7c5d79c907d36811282166d519604e3c62de86140a0989680df0` —
verified identical across two independent full `generate.py` runs, and
identical to the `GROUND_TRUTH_ONLY=1` fast path's output at the same scale
(see notes-infra.md). If this hash ever changes, either the corpus was
intentionally regenerated (update every consumer) or something drifted
unintentionally (investigate before trusting any downstream validator).

## Verification philosophy per task type

- **Recon/structural (01, 04)**: the validator drives the target directly
  (via `httpx`/`TargetClient`, never trusting the learner's own scraper
  output as an oracle) and compares against `target-spec.json`/
  `ground-truth.json` computed independently by `generate.py`'s pure
  builders — e.g. "does a full catalog crawl discover exactly
  `n_products` real product ids and exactly the honeypot ids listed in
  ground truth, with zero honeypot hits if the learner's crawler is
  well-behaved."
- **Data-quality contracts (02)**: pandera schema violations are checked
  against `bad_records.by_defect` from ground truth — a validator asserts
  the learner's quarantine sink contains EXACTLY the ids with each defect
  type (not a superset/subset), and the clean sink contains everything
  else, byte-parseable and schema-valid.
- **Change detection (03)**: the validator computes the true changed-id set
  per day from `ground-truth.json`'s `change_days` and compares against
  what the learner's fingerprinting pipeline reports — a NEGATIVE control
  matters here too: a validator that never re-fetches an UNCHANGED page
  across two days (to confirm the nonce alone doesn't trigger a false
  "changed") is not a complete check.
- **Cost/budget (05)**: cost is the MODELED unit from `cost_model`, never
  wall-clock time — a validator sums `http_cost`/`api_extra_cost` over the
  learner's actual fetch decisions and checks both the completeness ratio
  (>= `completeness_target`) AND the total modeled cost (<
  `all_render_cost`, ideally close to `mixed_cost`'s ballpark) — completeness
  alone is gameable by "always render everything."
- **Observability (06)**: Prometheus `/-/ready` and Grafana `/api/health`
  live checks are ALWAYS skip-if-down (`query_prometheus` returns `None`
  rather than raising) — the MUST-PASS check is that the learner's own
  `/metrics` endpoint, scraped by the `spider` Prometheus job, actually
  serves parseable Prometheus text-exposition content with the expected
  metric names; a live Grafana dashboard render is a nice-to-have, not a
  hard gate, since a learner's local Grafana provisioning can legitimately
  differ across runs.
- **Security-adjacent framing**: this module is NOT a security module in
  the sense modules 12's SQLi/JWT/secrets tasks are — header spoofing,
  rate-limit evasion, and honeypot avoidance here are "how a scraper
  behaves ethically/robustly under a hostile target," not an
  exploit-then-patch exercise. There is no "fix the target" task; the
  target's defenses are the FIXED environment the learner's client must
  behave well against.
