# Module 13 infra notes (wave-1 build + verification)

Host: Windows 11, Git Bash, uv, Docker Desktop (Docker 28.x / Compose v2).

## Commands run

```
cd 13-scraping-at-scale
uv lock                                   # 49 packages resolved
uv sync                                   # .venv created

SCALE=0.2 uv run python generate.py       # smoke test: 800 products, 28 sellers, 6 honeypots
GROUND_TRUTH_ONLY=1 SCALE=0.2 uv run python generate.py   # fast path -- identical ground-truth.json sha to the full run at the same scale

uv run python generate.py                 # SCALE=1.0, first run
sha256sum data/ground-truth.json
uv run python generate.py                 # SCALE=1.0, second run
sha256sum data/ground-truth.json          # identical -> deterministic

docker compose up -d --build              # target + prometheus + grafana
docker compose ps                         # all three healthy
```

## `uv lock` / `uv sync`

49 packages resolved incl. fastapi 0.139.2, uvicorn 0.51.0, httpx 0.28.1,
numpy 2.5.1, pandas 3.0.3, pandera 0.32.1, parsel 1.11.0, lxml 6.1.1,
beautifulsoup4 (via soupsieve/bs4), selectolax 0.4.11, prometheus-client
0.25.0, pyarrow 25.0.0, pyyaml 6.0.3, pytest 9.1.1.

## `generate.py` verification

At SCALE=1.0: `n_products=4000`, `n_sellers=140`, `honeypot_count=30`,
`bad_records=400` (67/67/67/67/66/66 across the 6 defect types).

**Cost model** (printed by `generate.py`, matches design.md's math exactly):

```
http_cost=1.0 api_extra_cost=7.0 render_cost=8.0 completeness_target=0.98
requires_detail_count=1191 requires_detail_fraction=0.2978   (target band 25-35%, met)
all_http_completeness=0.7023   (well below 0.98 -> FAILS the target, as intended)
all_render_completeness=1.0    all_render_cost=32000.0
mixed_completeness=1.0         mixed_cost=12337.0   (2.59x cheaper than all-render)
```

**Determinism**: `data/ground-truth.json` sha256 identical across two
independent full SCALE=1.0 runs, AND identical between the full run and
`GROUND_TRUTH_ONLY=1` at SCALE=0.2 (separate, smaller hash, not committed —
confirms the fast path never diverges from the full path's computed
values):

```
sha256(data/ground-truth.json) @ SCALE=1.0 =
335e94cae56e7c5d79c907d36811282166d519604e3c62de86140a0989680df0
```

**Category popularity** (Zipf, verified live at SCALE=1.0): electronics
(rank 0) has 1,492 of 4,000 products, by far the largest category, matching
the declared `w = 1/(rank+1)**1.1` ranking.

**Timing**: SCALE=1.0 generation (pure numpy, no DB/network) completes in
well under a second — no threaded/expensive step exists in this module
(unlike module 12's password hashing), since there is no shared database to
load.

## Docker stack verification (SCALE=1.0 data, `docker compose up -d --build`)

All three services reported healthy (`docker compose ps`):
`target` (health: healthy, via a curl healthcheck sending the required
browser UA + Accept-Language — see "Dockerfile gotcha" below), `prometheus`
(health: healthy, `/-/ready` = "Prometheus Server is Ready."), `grafana`
(no healthcheck configured, `/api/health` returns `{"database":"ok",
"version":"13.1.0",...}`).

### Header gate

- No headers: `GET /robots.txt` -> `403`.
- Browser UA + `Accept-Language: en-US` -> `200`, landing page content
  confirmed (`4000 products. <a href="/catalog">...`).

### JS-only fields (headless-render stand-in)

`GET /product/2` (html, resolved to markup v3/jsonld for this id): NO
`rating`/`shipping_info` anywhere in the response. `GET /api/product/2`:
`"rating":null,...,"shipping_info":{"free":true,"eta_days":2,
"carrier":"CargoLine"}` — `rating` is `null` because product 2's
`review_count == 0` (correctly NOT required for completeness).

### Honeypot

Reset client `hp-test-1`, `GET /product/4001` (first honeypot id) -> 200
decoy (`"Item Unavailable"`), `/__debug/client` shows
`"honeypot_hits":1,"banned":true`. Next request (`GET /catalog`) -> `403`
even with correct headers, confirming the ban persists. Also verified the
separate `/trap/{token}` vector (`GET /trap/6d410006`) flags the same way,
and that `/catalog?page=1` actually embeds the hidden honeypot links
(`class="hp">item 4001</a>`, `item 4002</a>`) plus the hidden trap link on
page 1.

### Rate limit (ORIGINAL wave-1 numbers, since retuned — see next section)

- Sequential 25-request burst on one fresh client: `200` x11, then a mix of
  `429`s (12 total violations) interspersed with a few more `200`s as the
  bucket slowly refills (`refill_per_sec=3.0`) — NOT yet banned
  (`rate_limit_violations":12 < ban_after_violations:15`).
- A 40-request burst on a fresh client: violations reach exactly 15, then
  EVERY subsequent request is `403` (`"banned":true`) — confirms
  sustained abuse crosses the ban threshold and the ban is sticky.
- A paced client (5 requests, 0.4s apart, well under the 3/s refill rate):
  all `200`, `"rate_limit_violations":0` — confirms a polite scraper is
  never penalized.

## Rate-limit retune (post wave-1 session)

The coordinator flagged the original numbers above as impractical: a
well-behaved crawler at `refill_per_sec=3.0` would take ~22 minutes to
sweep 4,000 products, too slow for both a learner and every validator that
crawls the full catalog. Retuned `data/target-spec.json`'s `rate_limit` (via
`generate.py`) to `capacity=25`, `refill_per_sec=50.0`,
`ban_after_violations=25`, keeping the honeypot instant-ban, header gate,
403/429 response shapes, and debug bypass all EXACTLY as they were.

```
sha256(data/ground-truth.json) BEFORE retune = 335e94ca...80df0
uv run python generate.py         # regenerated catalog.json + target-spec.json at SCALE=1.0
sha256(data/ground-truth.json) AFTER retune  = 335e94ca...80df0   -- UNCHANGED, as expected
                                                                      (rate_limit isn't a ground-truth key)
docker compose up -d --build target    # rebuilt + restarted with the new target-spec.json mounted
```

### Live re-verification: polite (paced) crawler vs. naive (unbounded) burst

**First finding, before settling on a reference pacer**: bounded
concurrency ALONE (an `asyncio.Semaphore`, no other pacing) does NOT cap
throughput on this target — request handling is sub-millisecond (in-memory
dict lookups, zero I/O), so `asyncio.gather` over all 4,000 ids through a
semaphore of 10 measured **~220 req/s**, 4.4x the 50 req/s refill ceiling,
and got banned (`rate_limit_violations=25, banned=true`) well before
finishing. A real "polite" crawler on this target needs an EXPLICIT
dispatch-rate pacer, not just a concurrency cap — documented in
design.md's "Rate-limit retune" section as a note for whoever authors task
01's reference/validator crawler.

**Second finding**: a naive fixed `await asyncio.sleep(interval)` between
dispatches is ALSO unreliable on Windows — the default asyncio event-loop
timer resolution (~15.6ms) quantizes short sleeps to tick multiples, so a
requested 45 req/s and a requested 58 req/s pace measured the IDENTICAL
actual ~32 req/s (both rounded up to a 2-tick interval), while a requested
90 req/s jumped straight to ~64 req/s (1 tick) and got banned. Fixed by
using a self-calibrating token pacer that accumulates fractional "tokens"
from REAL measured wall-clock elapsed time each wake (`time.perf_counter()`
deltas), rather than trusting any single `sleep()` call's requested
duration — converges to the target average rate regardless of the OS
timer's actual granularity.

**Final measured numbers** (SCALE=1.0, n_products=4,000, target rebuilt
with the new rate-limit params):

| crawler | mechanism | requests | elapsed | result |
|---|---|---|---|---|
| polite | concurrency=16 semaphore + self-calibrating pacer targeting 47 req/s, with 429-triggered backoff as a safety net | 4,000 (all real product ids) | **85.10s** (measured effective rate: 47.0 req/s) | ALL `200`, `rate_limit_violations=0`, `banned=false` |
| naive | `asyncio.gather` over 300 ids, zero pacing, zero backoff, fired all at once | 300 | **2.33s** | `28x 200 / 25x 429 / 247x 403` in the SAME burst, `rate_limit_violations=25`, `banned=true` |

The polite crawler's ~85s for a full 4,000-product sweep is the practical
floor for a ZERO-violation crawl given `refill_per_sec=50` is a hard
sustainable ceiling (4000/50 = 80s theoretical minimum; 85s includes a
small safety margin below that ceiling) — a dramatic improvement over the
original ~22 minutes, and the naive unbounded burst still gets banned
almost instantly (2.33s), confirming the burst/concurrency gate (not the
sustained rate) is what catches the abusive case, as intended.

Reference pacer scripts used for this verification (not committed — throw-
away, run from the scratchpad, never part of the module):
`polite_crawl.py` (concurrency=16 semaphore + `token_pacer()` async
generator dispatching by real elapsed time, with 429 backoff via
`Retry-After`) and `naive_burst.py` (plain `asyncio.gather` over N ids, no
pacing, no backoff, `return_exceptions=True`). Both use
`harness.common.TargetClient`-equivalent headers (`DEFAULT_USER_AGENT`/
`DEFAULT_ACCEPT_LANGUAGE`) plus `reset_client`/`get_client_state` from
`harness/common.py` to reset and read state through `/__debug/*`.

### Markup versions

`GET /product/1?v=1` (classic-div): visible `<span class="price">EUR
52.96</span>`. `?v=3` (jsonld): NO visible price text anywhere; price only
inside the `application/ld+json` script (`"price": 52.96, "priceCurrency":
"EUR"`). `?v=4` (data-island): price only inside `<script id="__DATA__"
type="application/json">` (`"price": 52.96, "currency": "EUR"`) — three
structurally distinct encodings of the SAME underlying record confirmed
live.

### Per-day change + volatile nonce

Product 9 (a day-1 changed id per ground truth): `price` 147.24 (day 0) ->
151.45 (day 1), all other fields identical except `_nonce` (fresh uuid4
each request, as expected). An UNCHANGED product (id 2): every field
byte-identical between `?day=0` and `?day=1` EXCEPT `_nonce` — confirms the
nonce is the only source of noise a fingerprint needs to strip.

### Bad records (all 6 defect types)

Probed one id per defect type directly against `/api/product/{id}`:

| id  | defect            | observed                                                    |
|-----|--------------------|--------------------------------------------------------------|
| 69  | `missing_price`    | no `"price"` key in the JSON at all                          |
| 101 | `price_na`         | `"price":"N/A"`                                               |
| 208 | `empty_title`      | `"title":""`                                                  |
| 70  | `negative_price`   | `"price":-75.89`                                              |
| 43  | `bad_currency`     | `"currency":"XYZ"`                                            |
| 11  | `truncated`        | `"description":"Pro Router by Cinderpe...[TRNC]<garbled>"`   |

All 6 confirmed exactly matching design.md's table.

### Observability stack

`curl http://localhost:9313/-/ready` -> `Prometheus Server is Ready.`
`curl http://localhost:9313/api/v1/targets` -> `prometheus` job `up`,
`spider` job `down` (EXPECTED — no learner scraper exposing `:9113/metrics`
exists yet; this is infra-only, task 06 doesn't exist). `curl
http://localhost:3313/api/health` -> `{"database":"ok",...}`.

## Gotchas / decisions

- **`python:3.12-slim` has no `curl`** — the target Dockerfile originally
  used only `pip install`, and the compose healthcheck (`curl -f ...`)
  stayed stuck at `health: starting` forever. Fixed by adding
  `apt-get install -y --no-install-recommends curl` to the Dockerfile. The
  healthcheck itself sends the required browser UA + `Accept-Language`
  explicitly (`curl -A "Mozilla/5.0 (healthcheck)" -H "Accept-Language:
  en-US"`) rather than exempting `/robots.txt` from the header gate — kept
  the gate's scope exactly "every route except `/__debug/*`" as designed,
  rather than adding a second bypass just for convenience.
- **Prometheus `spider` job target port (9113)** is a NEW convention this
  session introduces (not in CONVENTIONS.md's fixed-ports table, since it's
  a learner dev-server port like module 12's ephemeral API ports, not a
  docker-compose service) — documented in design.md and `prometheus.yml`'s
  own comment; task 06's author must either use exactly 9113 or update both
  files together.
- **Honeypot ids as a contiguous block above `n_products`** (rather than
  scattered ids within 1..n_products with an id->honeypot lookup) was
  chosen so both the app and any validator can classify "is this a
  honeypot" with a single range comparison — no set lookup, no risk of a
  honeypot id colliding with a real product id by construction.
- **Per-day change values are CUMULATIVE, not independent per-day
  redraws** — `build_change_days` walks days 1..4 in order maintaining
  running price/stock arrays, matching the spec's "changed vs the PREVIOUS
  day" wording literally; each day still uses its own independent
  `seed + day` rng stream for WHICH ids change and by how much, so a
  validator recomputing a single day doesn't need to replay earlier ones,
  it only needs the earlier ones' cumulative effect already folded in (which
  `ground-truth.json`'s per-day id lists let it reconstruct alongside
  `target-spec.json`'s actual values).
- **`review_count` (Poisson(0.357)) as the sole driver of "does this
  product require the render step"** is a deliberate authoring choice, not
  directly stated in the brief — it's what makes `js_only_fields` genuinely
  ALWAYS absent from HTML (a clean, unconditional rule) while still letting
  ~70% of products be "complete" from HTML alone (an HTML-visible signal,
  `review_count`, legitimately tells you nothing js-only is missing). The
  alternative (making the requirement itself random and undiscoverable)
  would make task 05's router unsolvable without cheating by rendering
  everything.
- **Stock state after this session**: `docker compose up` stack LEFT
  RUNNING (target/prometheus/grafana all healthy) per the task's explicit
  instruction. `data/` contains `catalog.json`, `target-spec.json`, AND the
  committed `ground-truth.json`, all at SCALE=1.0 (the two gitignored files
  are regenerable any time via `uv run python generate.py`; only
  `ground-truth.json` is tracked by git). No `scratch/`/`__pycache__`/
  `*-local.json` created or tracked.

## Public API signatures handed to task-author agents

`harness/common.py`:
```python
MODULE_ROOT, DATA_DIR, GROUND_TRUTH_PATH, CATALOG_PATH, TARGET_SPEC_PATH: Path
SEED = 131313
TARGET_DEFAULT_PORT, PROM_DEFAULT_PORT, GRAFANA_DEFAULT_PORT: int
DEFAULT_USER_AGENT, DEFAULT_ACCEPT_LANGUAGE: str

def not_passed(reason)
def passed(msg="")
def guarded(fn)
def _last_line(text)
def time_it(fn, *args, **kwargs)
def write_baseline(path, obj)
def read_baseline(path)
def load_ground_truth()
def load_catalog()
def load_target_spec()
def target_port() / target_base_url()
def prom_port() / prom_base_url()
def grafana_port() / grafana_base_url()
class TargetClient(client_id=None, base_url=None, headers=None, **httpx_kwargs)
def get_client_state(client_id, base_url=None)
def reset_client(client_id, base_url=None)
def query_prometheus(expr, base_url=None)
```

`generate.py`:
```python
def build_categories()
def build_sellers(seed, n)
def build_products(seed, n, n_sellers, seller_names, categories)
def build_bad_records(seed, product_ids, fraction=BAD_FRACTION, defect_types=None)
def build_honeypots(seed, n_products, count=HONEYPOT_COUNT_BASE, n_trap_tokens=TRAP_TOKENS_COUNT)
def build_change_days(seed, product_ids, baseline_price, baseline_in_stock, n_days=N_DAYS, fraction=CHANGE_FRACTION)
def build_markup_versions()
def build_cost_model(n_products, review_count, http_cost=HTTP_COST, api_extra_cost=API_EXTRA_COST, completeness_target=COMPLETENESS_TARGET)
```

## Deviations from the wave-1 spec, and why

- **Docker healthcheck sends explicit browser headers** rather than
  exempting `/robots.txt` from the header gate (see "Gotchas" above) — a
  scope-preserving choice, not a spec deviation in substance, but worth
  flagging since the spec's own bullet just says "healthcheck curl
  `/robots.txt`" without anticipating the header gate would apply to it too.
- **`js_only_fields` requirement is CONDITIONAL on `review_count > 0`**,
  not a blanket "always required" — necessary to hit the spec's own
  "~25-35% of products should require the render step" and "all-HTTP fails
  a completeness target ~0.98" numbers simultaneously; a blanket
  requirement would make either all-HTTP completeness collapse to ~0% (if
  js_only fields are unconditionally required) or the mixed router provide
  no savings at all (if every product needs rendering). Documented in
  design.md's cost-model section.
- Everything else in the spec (ports, file layout, catalog/target-spec/
  ground-truth key names, markup version count and encodings, honeypot/
  bad-record/change-day mechanics, harness function set, Prometheus/Grafana
  provisioning shape) was implementable exactly as specified — no other
  deviations.
