# Module 11 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
shared harness API every task and validator depends on, the mock-peer
knobs/stats semantics, the corpus schema and RNG draw order, the committed
ground-truth values, and the verification philosophy per task type.

This file is the shared contract for every agent working on this module
(infra, generator, task authors, validators). If you change something here,
regenerate and reverify and update every consumer in the same change.

## No docker stack

Module 11 is pure Python (`asyncio`, `aiohttp` for the mock peer and client
requests, `psutil`/`numpy` where noted). There is no `docker-compose.yml` and
no ports table entry in `CONVENTIONS.md` — nothing here binds a fixed host
port. `harness/peer.py`'s mock server always binds `127.0.0.1:0` (OS-assigned
ephemeral port), so parallel task runs never collide.

## Harness API (`harness/common.py`)

Every third-party import (`asyncio` excluded — it's stdlib) is lazy inside
the function that needs it; importing `harness.common` has zero side effects
and requires nothing running.

```python
MODULE_ROOT: Path                    # 11-python-concurrency/
DATA_DIR: Path                       # MODULE_ROOT / "data"
GROUND_TRUTH_PATH: Path              # DATA_DIR / "ground-truth.json"

def not_passed(reason) -> NoReturn   # print "NOT PASSED: <reason>", sys.exit(1)
def passed(msg="") -> NoReturn       # print "PASSED[: msg]", sys.exit(0)
def guarded(fn) -> Callable          # decorator: unexpected exceptions (incl. NotImplementedError) -> NOT PASSED; SystemExit re-raised
def _last_line(text) -> str          # last non-empty line of a stream/error text

def time_it(fn, *a, **k) -> tuple    # (result, elapsed_seconds) via time.perf_counter
def write_baseline(path, obj) -> Path  # write gitignored *-local.json under MODULE_ROOT (relative paths resolved against it)
def read_baseline(path) -> dict|None   # read it back, or None if absent

def load_ground_truth() -> dict      # reads GROUND_TRUTH_PATH or NOT PASSED("...run generate.py first")

def run_async(coro) -> Any           # asyncio.run(coro); NOT PASSED if a loop is already running in this thread
def snapshot_tasks() -> set[asyncio.Task]         # all_tasks() minus the current task; needs a running loop
def leaked_tasks(before: set) -> list[asyncio.Task]  # tasks alive now, not in `before`, not done()

def measure_peak_memory(async_fn, *a, **k) -> tuple  # (result, peak_bytes) via tracemalloc around asyncio.run(async_fn(*a,**k))
def rss_bytes() -> int               # psutil current-process RSS, secondary signal
```

Design notes for task authors:

- **`leaked_tasks` usage pattern**: call `before = snapshot_tasks()` and
  `after_check = leaked_tasks(before)` from *inside* the same running loop
  as the code under test (e.g. within the coroutine passed to `run_async`,
  or within a `pytest-asyncio` test function) — both need `asyncio.
  all_tasks()`, which raises outside a running loop. A validator that needs
  to assert "no leaks" typically does:
  ```python
  async def _check():
      before = snapshot_tasks()
      await code_under_test()
      leaked = leaked_tasks(before)
      assert leaked == [], f"leaked tasks: {leaked}"
  run_async(_check())
  ```
- **`measure_peak_memory` / `run_async` constraint**: both drive their own
  `asyncio.run()` internally, so neither may be called from inside an
  already-running loop (that's a bug in the calling code, not something to
  special-case — `run_async` reports it as NOT PASSED; `measure_peak_memory`
  lets asyncio's own RuntimeError surface since it's an authoring error, not
  a learner-code condition it needs to diagnose).
- **`measure_peak_memory` reports traced allocation, not RSS.** Use it (not
  `rss_bytes`) for any assertion like "the bounded version's peak memory is
  within Nx of a small constant" (task 04, backpressure) — tracemalloc's peak
  is portable and reproducible; RSS varies by allocator/OS and is offered
  only as a secondary/diagnostic signal.
- **`guarded`** has identical semantics to module 10's — it wraps a *sync*
  validator entry point. A validator whose body is async should put the
  `async def` + `run_async(...)` call inside the function `guarded` wraps,
  not decorate an `async def` directly.

## Mock peer (`harness/peer.py`)

```python
class PeerStats:                     # dataclass
    total_requests: int = 0
    max_observed_concurrency: int = 0
    error_responses: int = 0
    throttled: int = 0

class Peer:
    base_url: str                    # "http://127.0.0.1:<port>"
    stats: PeerStats
    def url(self, path) -> str       # base_url + ("/" + path if not path.startswith("/") else path)

@asynccontextmanager
async def mock_peer(
    *, base_latency=0.05, jitter=0.0, max_concurrency=None,
    rate_per_sec=None, error_rate=0.0, seed=0, corpus=None,
) -> AsyncIterator[Peer]
```

Binds `127.0.0.1:0` via a self-created `socket` (bound before `aiohttp.web.
SockSite` starts, so the port is known immediately — avoids relying on
private `AppRunner`/`TCPSite` internals to read back an ephemeral port).

### Request handling order (exact, per `GET /<path>`)

1. `stats.total_requests += 1` (every arrival counts, even ones about to be
   throttled).
2. **Concurrency gate** (if `max_concurrency` set): if `in_flight + 1 >
   max_concurrency`, return 429 and `stats.throttled += 1` — **without**
   incrementing `in_flight`. This ordering is deliberate: it guarantees
   `max_observed_concurrency <= max_concurrency` always holds (a naive
   "increment first, check second" lets `max_observed_concurrency` spike one
   above the cap on the arrival that gets rejected — caught by the infra
   probe, see notes-infra.md).
3. `in_flight += 1`; if `in_flight > stats.max_observed_concurrency`, update
   the max. Everything from here down runs inside a `try/finally` that
   decrements `in_flight` on the way out (including on cancellation/error).
4. **Rate gate** (if `rate_per_sec` set): sliding 1-second window via a
   `deque` of `time.monotonic()` arrival timestamps (pruned each call); if
   the count after appending this arrival exceeds `rate_per_sec`, return 429
   and `stats.throttled += 1`. Only requests that passed step 2 reach this
   gate — a concurrency-rejected request does not consume rate budget.
5. `await asyncio.sleep(base_latency + uniform(0, jitter))` — the simulated
   slow-peer latency. Drawn from the peer's own `random.Random(seed)`.
6. **Error roll** (if `error_rate > 0`): `rng.random() < error_rate` ->
   return 500, `stats.error_responses += 1`.
7. Otherwise 200: `corpus.get(path)` if `corpus` given and path present
   (bytes/bytearray returned raw, else JSON-encoded), else the deterministic
   `{"path": path}`.

Determinism caveat: the peer's RNG is a single shared `random.Random(seed)`
consumed in per-request arrival order. Under real concurrent load, coroutine
scheduling order is not perfectly deterministic across OS/Python versions,
so the *exact* draw-to-request assignment can vary run-to-run even at a
fixed seed — only the aggregate distribution (error rate, jitter
distribution) is reproducible. Do not write a task assertion that depends on
"request N gets exactly draw N."

## Corpus + ground truth (`generate.py`)

`build_corpus(seed, n) -> dict[str, dict]` is pure (numpy + stdlib only, no
file I/O). Seed **111111**, fixed draw order:

- **G1** `category_idx = rng.choice(6, size=n, p=category_weights())` — Zipf
  `1/rank^1.1` over `CATEGORIES = ["electronics", "home-goods", "kitchen",
  "toys", "sporting-goods", "apparel"]` (in that rank order, most to least
  popular).
- **G2** `z = rng.normal(size=n)` -> `price = round(exp(ln(median_cat) +
  sigma_cat * z), 2)`, clipped `>= 0.5`. Per-category `(median, sigma)`:
  electronics `(120.0, 0.9)`, home-goods `(45.0, 0.7)`, kitchen `(35.0,
  0.6)`, toys `(25.0, 0.6)`, sporting-goods `(55.0, 0.7)`, apparel `(30.0,
  0.6)`.

**Do not reorder G1/G2** without regenerating and updating every consumer
(the committed ground truth is a direct function of this draw order).

Each page: key `"/p/{i}"` (1-based `i`, `product_id = i`), value `{
"product_id": int, "category": str, "price": float }`. `n_pages = round(3000
* SCALE)`.

`data/corpus.json` (gitignored): one JSON object, `path -> record`, written
with `json.dumps(corpus, indent=2)` — insertion order is `i = 1..n`, so byte
output is deterministic given the seed (Python dicts preserve insertion
order; no `sort_keys` needed since insertion order already is sorted-by-i).

`data/ground-truth.json` (COMMITTED), computed by iterating the built corpus
(`_ground_truth`, never hand-computed):

```
{
  "seed": 111111,
  "scale": 1.0,
  "n_pages": 3000,
  "categories": ["electronics","home-goods","kitchen","toys","sporting-goods","apparel"],
  "count": 3000,                       # == n_pages, computed independently by iterating
  "price_sum": 324536.21,              # round-2 sum of price over all pages
  "per_category_count": {
    "electronics": 1316, "home-goods": 616, "kitchen": 389,
    "toys": 279, "sporting-goods": 202, "apparel": 198
  }
}
```

Verified SCALE=1.0 values above (see notes-infra.md for the reproduction
commands and sha256). `price_sum` and any other money figure must be compared
with a small float tolerance in validators, never exact-decimal equality.

## Verification philosophy per task type

- **Structural / behavioral** (most tasks): `leaked_tasks(before) == []`
  after the code under test runs; `Peer.stats.max_observed_concurrency <=`
  the configured cap; result correctness against `load_ground_truth()` or a
  validator-computed reference (e.g. via `build_corpus` in-memory, mirroring
  module 10's pure-builder pattern) with float tolerance on money fields.
- **Memory-bounded** (task 04, backpressure): peak via `measure_peak_memory`
  compared as a *ratio* against an unbounded/naive baseline run — never an
  absolute byte count (allocator/interpreter-version dependent).
- **Relative timing only** (tasks 06 GIL-decision-matrix, 08 profiling): a
  `baseline.py` run first, writing a gitignored `*-local.json` via
  `write_baseline`; later checks compare against that file via
  `read_baseline`, never an absolute wall-clock number. This is the only
  place module 11 does timing assertions.
- **Profiling** (task 08 specifically): py-spy attaches to a real running
  process (`py-spy record`/`dump --pid`), so there is no harness mock for
  it — the task launches an actual async app and profiles it externally.
  Verification there is necessarily more manual/structural (e.g. "the
  flamegraph/output file exists and mentions the hot function") than a
  numeric assertion.

## Per-task namespacing

Unlike module 10 (shared Redis/Mongo/Postgres across 8 tasks needing a
`s10:tNN:` / `tNN_` / `t06` convention), module 11 has **no shared external
state** — no database, no fixed ports (the mock peer is ephemeral-port
per-instantiation). Each task confines its own scratch files to a gitignored
`scratch/` or `scratch-*/` directory under its own task folder; no
cross-task namespacing scheme is needed.
