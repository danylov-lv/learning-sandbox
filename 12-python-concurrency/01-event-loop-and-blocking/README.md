# 01 -- Event Loop and Blocking

## Backstory

You inherited a scraper from a teammate who left the team. It's called
`fetch_all(base_url, paths, blocking_parse)`, it's `async def`, it `await`s
things, and the commit that introduced it is titled "make fetcher
concurrent." Someone benchmarked it against the old synchronous version once,
shrugged, and moved on -- it wasn't obviously faster, but it wasn't obviously
broken either, and the ticket got closed.

It's still roughly as slow as the synchronous version it replaced, and
occasionally slower, and nobody has figured out why, because nothing in the
code *looks* wrong. It has `async`/`await` all over it. It's just that
`async def` on a function doesn't make the work inside it concurrent -- it
makes the function *awaitable*, which is a different thing entirely. Two
separate mistakes are hiding in a fetcher that looks fine on a skim:

1. **Sequential awaiting dressed up as concurrency.** A `for` loop that does
   `await session.get(...)` once per path suspends the whole coroutine until
   that one response lands, then moves to the next path -- and only then does
   the next request even get sent. Nothing is ever in flight alongside
   anything else. N requests at `latency` seconds apiece costs roughly
   `N * latency` wall-clock time, same as a blocking client, just spelled
   with `await`.
2. **A blocking call running straight on the loop's own thread.** Even after
   requests go out concurrently, each response still has to get parsed. If
   that parse step is a plain synchronous, blocking function -- a blocking
   I/O call, or a native/C-extension parser that releases the GIL while it
   runs -- no `await` inside it, no yield point -- and you call it directly from a
   coroutine, it runs on the *one* OS thread the event loop uses to do
   everything: poll sockets, run other coroutines, fire timers. For as long
   as that call is on the stack, nothing else in the process moves. Not the
   other N-1 responses waiting to be parsed. Not some unrelated coroutine
   just trying to emit a heartbeat every 10ms. The loop isn't crashed or
   deadlocked -- it's just not scheduled to run anything until this one
   synchronous call returns.

Either mistake alone is enough to erase the benefit of using asyncio at all.
Together, they produce a fetcher that reads as concurrent, quacks as
concurrent, and performs like a `for` loop with extra ceremony.

## What's given

- `src/fetcher.py` -- a `fetch_all(base_url, paths, blocking_parse)` stub.
  It currently `raise NotImplementedError`. The module docstring narrates
  the broken version above in more detail and the function docstring spells
  out the exact contract your implementation has to satisfy -- no solution
  code, but the two failure modes and the four requirements are laid out
  precisely. Read it before writing anything; it also documents exactly
  what `blocking_parse` is (a black-box synchronous callable you're handed,
  not something you write).
- `tests/validate.py` -- the validator. Read it too; it's not just a
  correctness check, and understanding *how* it detects "loop got starved"
  (a concurrently-running heartbeat coroutine whose tick count would tank if
  the loop thread ever gets monopolized) will save you time versus
  discovering it by trial and error.
- `harness/peer.py` (module root, shared, do not modify) -- the mock peer
  your fetcher talks to. You don't need to read its internals to complete
  this task; `fetch_all` only ever sees `base_url` and needs a plain
  `aiohttp.ClientSession` pointed at it.
- `harness/common.py` (module root, shared, do not modify) -- `run_async`,
  `snapshot_tasks`, `leaked_tasks`, the pass/fail printing. The validator
  uses these; fair game to poke at by hand while developing, not something
  you need to call from `fetcher.py` itself.

## What's required

Implement `async def fetch_all(base_url, paths, blocking_parse)` in
`src/fetcher.py` so that:

1. All paths are fetched **concurrently** -- in flight against the peer at
   the same time, not queued one after another behind sequential `await`s.
2. `blocking_parse` is **never called directly on the event-loop thread**.
   It has to be handed off somewhere that runs it off that thread while the
   loop stays free to service everything else, with the result awaited back
   into your coroutine.
3. The returned dict is complete and correctly keyed: every path in `paths`
   maps to `blocking_parse` applied to *that path's own* response body.
4. No task or future is left dangling -- whatever you create must be
   awaited (directly, or via a gather/TaskGroup) before `fetch_all` returns.

You have design freedom in exactly which primitives you reach for, as long
as those four properties hold. The docstring in `src/fetcher.py` gives you
the full contract; the validator checks all four properties independently
and will tell you specifically which one failed.

## Completion criteria

Run, from this task's directory:

```bash
cd 01-event-loop-and-blocking
uv run python tests/validate.py
```

It:

- Fetches a batch of paths against the mock peer and checks the returned
  dict against an independently-computed expected result -- every path
  present, correctly keyed, correctly parsed.
- Checks the peer's own recorded stats for how many requests it saw
  simultaneously in flight -- a sequential-await fetcher pins this at 1 no
  matter how the rest of the code is written, so this alone catches mistake
  #1 from the backstory.
- Runs a heartbeat coroutine concurrently with your `fetch_all()` call and
  counts how many times it ticks. If `blocking_parse` runs inline on the
  loop thread, the loop can't service the heartbeat's timer while it's
  busy, and those ticks are permanently lost -- `asyncio.sleep` doesn't
  "catch up" on missed wakeups. This is how the validator catches mistake
  #2 without asserting any absolute wall-clock time.
- Confirms nothing you spawned was left running afterward.
- Prints `PASSED` with the observed concurrency and heartbeat tick count, or
  `NOT PASSED: <reason>` and exits 1 on any failure -- including the stub
  still raising `NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- How the asyncio event loop schedules coroutines -- cooperative
  single-threaded scheduling, and exactly what "yielding control" means at
  an `await` point
- `asyncio.gather` and `asyncio.TaskGroup` for concurrent awaiting of
  multiple coroutines
- `asyncio.to_thread` and `loop.run_in_executor` for offloading a
  synchronous, blocking callable off the event-loop thread
- Why `time.sleep` and `asyncio.sleep` are not interchangeable inside a
  coroutine, and what "blocking the loop" costs every *other* coroutine in
  the process while it happens
- `aiohttp.ClientSession` basics -- issuing concurrent GETs, reading
  response bodies

## Off-limits

`.authoring/design.md` (module root) holds the harness API contract,
mock-peer semantics, and generation details for the whole module --
spoilers. Don't read it before finishing this task.
