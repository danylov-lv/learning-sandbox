# Module 11 infra notes (wave-1 build + verification)

Host: Windows 11, Git Bash, uv 0.10.9, Python 3.14.0 (resolved by uv, module
requires `>=3.11`, no docker involved — pure Python module).

## Commands run

```
cd 11-python-concurrency
uv sync                                          # 19 packages installed; uv.lock written
uv run python -c "import harness.common, harness.peer"   # imports clean, no side effects
uv run python generate.py                        # SCALE=1.0
sha256sum data/ground-truth.json data/corpus.json
uv run python generate.py                        # re-run
sha256sum data/ground-truth.json data/corpus.json  # identical both times
uv run python scratch/probe.py                   # throwaway verification, then scratch/ deleted
git check-ignore -v 11-python-concurrency/data/corpus.json          # ignored (data/*)
git check-ignore -v 11-python-concurrency/data/ground-truth.json    # NOT ignored (!data/ground-truth.json), exit 0 with no match printed as ignored -> confirmed trackable
```

`uv sync` resolved: aiohttp 3.14.1, aiohappyeyeballs 2.7.1, aiosignal 1.4.0,
attrs 26.1.0, colorama 0.4.6, frozenlist 1.8.0, idna 3.18, iniconfig 2.3.0,
multidict 6.7.1, numpy 2.5.1, packaging 26.2, pluggy 1.6.0, propcache 0.5.2,
psutil 7.2.2, py-spy 0.4.2, pygments 2.20.0, pytest 9.1.1, pytest-asyncio
1.4.0, yarl 1.24.2.

## generate.py verification (SCALE=1.0)

- Wrote `data/corpus.json` (3000 pages, one JSON object path->record),
  `data/ground-truth.json` (committed).
- **Deterministic**: two consecutive runs produced byte-identical files —
  `ground-truth.json` sha256
  `ab2a3e983ba833643c71b3d53f0f20eed5e87200b91799ca66147e08e0eb5343`,
  `corpus.json` sha256
  `ff46e7ea0022aec966f401747907d5683ed644e05efe47c4448e2869c5fd5ec0`.
- Ground truth (SCALE=1.0):
  ```
  n_pages = 3000
  price_sum = 324536.21
  per_category_count = {
    "electronics": 1316, "home-goods": 616, "kitchen": 389,
    "toys": 279, "sporting-goods": 202, "apparel": 198
  }
  ```
  (Zipf-skewed toward electronics, as designed — matches `1/rank^1.1` over
  the 6-category list.)

## scratch/probe.py — what it proved, then was deleted

Three checks, all passing before deletion:

1. **Concurrency cap**: `mock_peer(base_latency=0.1, max_concurrency=5,
   seed=42)`, 50 concurrent `aiohttp` GETs via `asyncio.gather`. Result:
   `max_observed_concurrency=5`, `throttled=45`, `total_requests=50`, and
   the client observed 45 responses with status 429. This is the tight
   invariant the design enforces (see design.md "Concurrency gate" ordering)
   — every one of the 45 excess arrivals was rejected before touching
   `in_flight`, so the peak never exceeded the cap by even one.
2. **Peak memory**: `measure_peak_memory` around a coroutine allocating
   500,000 `object()` instances returned `peak_bytes=12177609` (~12.2MB) —
   plausible (roughly right order of magnitude for 500k small Python
   objects' tracked allocations) and nonzero, proving tracemalloc wiring
   works end-to-end through `asyncio.run`.
3. **Leaked-task detection**: `snapshot_tasks()` before creating an orphaned
   `asyncio.create_task(leaker())` (never awaited or cancelled by the
   caller), then `leaked_tasks(before)` correctly returned `[<the orphaned
   Task>]`. After explicitly cancelling and awaiting it, a second
   `leaked_tasks(before)` call correctly returned `[]` — proves the helper
   distinguishes "still running, never touched" from "cleaned up."

## Gotchas / decisions

- **First concurrency-gate design was wrong.** Initial implementation
  incremented `in_flight` at handler entry *before* checking
  `max_concurrency`, matching the task prompt's literal phrase "increment an
  in-flight counter at handler entry, record the max, decrement in a
  finally." Under real concurrent load this let `max_observed_concurrency`
  spike one above the cap (the arrival that gets rejected still bumped the
  counter before the check ran) — the probe caught this immediately (`max_
  observed_concurrency=6` with `max_concurrency=5`). Fixed by gating
  *before* incrementing: a request that would exceed the cap is rejected
  without ever touching `in_flight`, so `max_observed_concurrency <=
  max_concurrency` is now a hard invariant, not a probabilistic one. See
  design.md's "Request handling order" for the corrected, exact sequence.
- **Ephemeral port**: bound our own `socket` to `("127.0.0.1", 0)` and
  passed it to `aiohttp.web.SockSite` rather than using `TCPSite(runner,
  "127.0.0.1", 0)` and reading the port back off private `AppRunner`/
  `TCPSite` internals (`_server.sockets[0]`) — `SockSite` is public API and
  the port is known immediately from `sock.getsockname()`, before the site
  even starts.
- **`measure_peak_memory` / `run_async` both call `asyncio.run()`
  internally** — neither may be invoked from inside an already-running
  event loop. This matches `run_async`'s documented NOT PASSED guard; for
  `measure_peak_memory` the underlying `RuntimeError` is left to surface
  as-is since it signals an authoring bug in the calling code, not a
  learner-code condition worth a friendlier message.
- **No aiohttp-on-Windows surprises observed** — `SockSite` + `AppRunner`
  started and tore down cleanly across every probe run, no leftover
  `TimeoutError`/`WinError 10048` (address in use) since every run gets a
  fresh ephemeral port.
- **py-spy** (task 08) was `uv sync`'d successfully (0.4.2) but not exercised
  here — attaching to a live process needs a target process and is a task-08
  concern, not infra. Flag for task authors: on Windows, py-spy attach to
  another process typically needs the target and profiler to have matching
  privilege (an elevated shell is the simplest fix if `py-spy dump --pid
  <pid>` reports a permissions error) — mention this in task 08's README.
- **tracemalloc peak semantics**: `tracemalloc.get_traced_memory()` returns
  `(current, peak)` since `tracemalloc.start()` was called (or since the
  last `reset_peak()` in 3.12+) — `measure_peak_memory` starts fresh each
  call (`tracemalloc.start()` then `stop()` in a `finally`), so the peak is
  scoped exactly to that one call, not cumulative across multiple calls in
  the same process.
- **`git status` sanity check**: `11-python-concurrency/data/corpus.json`
  reported ignored by `.gitignore:2:data/*`; `ground-truth.json` reported as
  a match against the negation rule `.gitignore:3:!data/ground-truth.json`
  (i.e. NOT ignored, trackable) — both as intended, matching module 10's
  `.gitignore` structure exactly.

## Public API signatures handed to task-author agents

See `.authoring/design.md` for the full annotated contract (semantics for
each parameter/return, the gate-ordering rationale for the mock peer, and
the corpus/ground-truth schema). The `def`/context-manager lines,
unannotated, for quick reference:

`harness/common.py`:
```python
MODULE_ROOT: Path
DATA_DIR: Path
GROUND_TRUTH_PATH: Path

def not_passed(reason)
def passed(msg="")
def guarded(fn)
def _last_line(text)
def time_it(fn, *args, **kwargs)
def write_baseline(path, obj)
def read_baseline(path)
def load_ground_truth()
def run_async(coro)
def snapshot_tasks()
def leaked_tasks(before)
def measure_peak_memory(async_fn, *args, **kwargs)
def rss_bytes()
```

`harness/peer.py`:
```python
class PeerStats:  # dataclass: total_requests, max_observed_concurrency, error_responses, throttled

class Peer:
    def __init__(self, base_url, stats)
    def url(self, path)

@asynccontextmanager
async def mock_peer(*, base_latency=0.05, jitter=0.0, max_concurrency=None,
                     rate_per_sec=None, error_rate=0.0, seed=0, corpus=None)
```

`generate.py`:
```python
def build_corpus(seed, n)   # pure: dict["/p/{i}"] -> {product_id, category, price}
```
