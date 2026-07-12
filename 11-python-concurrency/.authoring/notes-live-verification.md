# Module 11 live verification (final wave)

Host: Windows 11, Git Bash, uv 0.10.9, Python 3.14.0, **ProactorEventLoop**
(the default on Windows). Pure-Python module, no docker. This wave generated
the three missing tasks (06 GIL matrix, 08 py-spy, 09 capstone), completed the
three partial tasks (01, 04, 07), and fixed two environment-specific validator
bugs that only surface on Windows/Proactor.

## Stock-fail sweep (all 11 validators, untouched stubs)

Every validator prints a single clean `NOT PASSED: …` line, exit 1, **zero
traceback lines** (`@guarded` holds across the whole module):

- 01/02/03/04/05/07 -> `NOT PASSED: scaffold not implemented yet (NotImplementedError)`
- 06 -> `NOT PASSED: … baseline-local.json not found -- run \`uv run python baseline.py\` first …`
- 08 -> `NOT PASSED: event loop stalled … profile the live process with py-spy to find it`
- 09 CP1/CP2 -> `NOT PASSED: scaffold not implemented yet (NotImplementedError)`
- 09 CP3 -> `NOT PASSED: DESIGN.md: section '…' still contains the shipped '(fill in' placeholder …`

## Pass-paths proven (throwaway reference impls in gitignored scratch/, then reverted byte-identical)

- **01**: offloaded `gather` + `to_thread(blocking_parse)` -> PASSED, heartbeat
  `frac ≈ 1.0`; inline parse -> NOT PASSED on check 3, `frac ≈ 0.54` (see fix B).
- **04**: bounded `Queue(maxsize)` + TaskGroup -> PASSED, peak-mem ratio N->4N
  ≈ 0.99x; an unbounded-list reference shows ≈ 3.92x and correctly FAILS the
  ~2.2x threshold (the check discriminates).
- **05**: semaphore + rate-limiter -> PASSED, `throttled=0`, relocated leak
  check does not false-flag.
- **06**: correct runners -> PASSED. Measured on a 12-core box (`CPU_N=2e6`,
  `IO_DELAY=0.08`): cpu_bound seq 2.12s / threads 2.25s / **processes 0.81s**
  (process speedup 2.60x vs thread 0.94x — the GIL, demonstrated); io_bound
  seq 0.64s / threads 0.082s / asyncio 0.083s (~7.8x). Asserted margins
  (MIN_PROCESS_SPEEDUP=1.5, MAX_THREAD_SPEEDUP=1.3, MIN_IO_CONCURRENT=3.0)
  have comfortable headroom.
- **07**: bounded `to_thread` offload, input order preserved -> PASSED
  (heartbeat calibrated to this machine's achievable rate); an inline
  reference correctly FAILS the responsiveness check.
- **08**: culprit is `compute_signature` (app.py) run inline on the loop.
  py-spy **attached cleanly on this Windows host, no elevation** — `py-spy
  dump --pid` caught `compute_signature (app.py:…)` at the top of the
  active+gil stack 3/3; `py-spy record` produced a valid SVG. Validator does
  NOT itself run py-spy (portability) — it gates on the behavioral heartbeat
  check + an ANSWER.md content gate. Uses `CONCURRENCY=1` so a fixed run's
  heartbeat (~0.63) separates cleanly from the broken run's (~0.42); at higher
  concurrency GIL contention among offloaded threads collapses the signal.
- **09 capstone**: correct semaphore + bounded-queue + TaskGroup + per-attempt
  timeout + retry -> all three checkpoints PASSED. CP1 `count=3000
  price_sum=324536.21 max_observed_concurrency=24` == committed ground truth
  (per-category counts exact). CP2 (`error_rate=0.2` + jitter) converges to the
  identical aggregate across repeated runs despite ~755 injected 500s, cap
  held, no leaks. CP3 gates DESIGN.md then re-runs CP1+CP2 green. Subprocess
  timeouts are 600s outer safety wrappers, never a correctness gate on
  wall-clock.

## Two Windows/Proactor bugs found and fixed this wave

### Fix A — peer accept-loop task false-flagged as leaked (tasks 01 and 05)
Under ProactorEventLoop, `harness/peer.py`'s in-process aiohttp server keeps a
pending-accept **Task** (`IocpProactor.accept.<locals>.accept_coro`, from
`asyncio/windows_events.py`) whose identity churns per accepted connection. A
validator that snapshots `before = snapshot_tasks()` *inside* `async with
mock_peer(...)` and then calls `leaked_tasks(before)` while the peer is still
running ALWAYS sees a "new, not-done" accept task and false-flags it — for ANY
implementation that makes even one request (reproduced with a 4-line bare
aiohttp probe, no learner code involved). On Linux/selector this never happens
because the accept is a callback, not a Task — which is why every prior
(Linux-verified) module missed it; module 11 is the first with an in-process
server verified on Windows. **Fix (validator-only, no `harness/` change):** take
the `before` snapshot BEFORE entering `mock_peer` and check `leaked_tasks`
AFTER the peer context fully exits, so the check spans the peer's whole
lifetime and its accept task is torn down. The capstone (`validate_cp1.py`)
established this pattern; tasks 01 and 05 were retrofitted to match. `harness/
common.py`'s `leaked_tasks`/`snapshot_tasks` were left unchanged (correct as
documented — the fix is about WHERE the snapshot is taken).

### Fix B — task 01 heartbeat check couldn't discriminate + false premise
Task 01 originally used a pure-Python **CPU-bound** `blocking_parse` stand-in.
Offloading pure-Python CPU work to threads does NOT free the event loop (the
GIL is held; the default pool's ~16 threads all contend), so a correct
offloaded solution and a broken inline one produced *identical* heartbeat ticks
(~10 each on this box) — the check was meaningless, and the task's implied
premise ("offload the CPU parse and the loop stays responsive") is technically
false (that GIL nuance is task **06**'s job). Reframed the blocking work as a
**GIL-releasing** blocking call — blocking I/O, or a native/C-extension parser
(lxml/orjson) that releases the GIL — which is the realistic "blocking call on
the loop" asyncio footgun anyway. Validator's `blocking_parse` now does a tiny
deterministic hash + `time.sleep(0.006)`; check 3 calibrates this machine's
achievable solo heartbeat rate (Windows caps ~64 Hz vs a 100 Hz theoretical,
so a fixed `elapsed/interval` threshold is unreachable) and asserts `frac =
ticks/(elapsed*solo_rate) >= 0.75`. Measured: offloaded ≈ 1.0, inline ≈ 0.54 —
wide, stable margin. Learner-facing "CPU-bound" wording in `src/fetcher.py`,
`README.md`, and `hint-1.md` was retargeted to "blocking (I/O / GIL-releasing
native)" so the lesson is truthful.

### Incidental — task 05 src was not a stub
`05-semaphore-rate-limiting/src/fetcher.py` shipped a leftover, actually-broken
full implementation (raised `ExceptionGroup`) instead of `raise
NotImplementedError`, despite its docstring promising the stub shape. Restored
to a proper stub (matches the module convention; grep-verified all `src/`
learner files now end in `raise NotImplementedError`, except the intentional
non-stubs `06/src/workloads.py` (provided) and `08/src/app.py` (the broken app
the learner profiles and fixes)).

## Stock state at commit
All 11 validators fail cleanly; no reference solutions committed anywhere;
`ANSWER.md`/`DESIGN.md` unfilled templates; `data/ground-truth.json` sha
`ab2a3e98…5343` (== wave-1), regenerates deterministically; no `scratch/`,
`*-local.json`, or `__pycache__` tracked.
