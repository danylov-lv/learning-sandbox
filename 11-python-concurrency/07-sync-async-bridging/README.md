# 07 -- Sync/Async Bridging

## Backstory

This task is two related bugs, not one, and each direction between sync and
async code breaks in its own way.

**Bug 1 -- calling blocking code FROM an async service.** Somewhere in a
service that's supposed to stay responsive, someone reaches for a
synchronous, genuinely-blocking third-party function (a driver doing
blocking network I/O, a CPU-bound transform, a library with no async variant
at all) and calls it directly on the hot path:

```python
async def process_batch_broken(items, blocking_lib):
    results = []
    for item in items:
        results.append(blocking_lib(item))  # BUG
    return results
```

This "works" in the sense that it returns the right answer. But
`blocking_lib(item)` never `await`s anything, so it never yields control
back to the event loop. The event loop is a single thread cooperatively
multiplexing everything -- every other coroutine, every pending I/O
callback, every timer -- and a synchronous call that blocks for real time
just occupies that one thread until it returns. From the outside, the
service looks completely frozen for exactly as long as `blocking_lib` takes,
once per item.

**Bug 2 -- calling the async service FROM synchronous code.** Suppose the
fixed, offloading-aware coroutine above is the thing you actually need to
call, but the caller is ordinary synchronous code -- a CLI entry point, a
plain function, a test -- with no event loop of its own:

```python
def sync_caller_broken(items, blocking_lib, max_workers):
    return process_batch(items, blocking_lib, max_workers)  # BUG: returns
    # an unawaited coroutine object, never actually runs
```

Calling a coroutine function only builds a coroutine object; nothing
executes until something drives it on an event loop.

## What's given

- `src/bridge.py` -- two stubs, both `raise NotImplementedError`:
  - `async def process_batch(items, blocking_lib, max_workers) -> list`
    (fixes bug 1)
  - `def sync_entrypoint(items, blocking_lib, max_workers) -> list` (fixes
    bug 2)

  The module docstring and each function's docstring spell out the exact
  guarantees required -- read `src/bridge.py` in full before starting; no
  solution code lives there.
- `harness/common.py` (module root, shared, do not modify) -- in particular
  `run_async`, used by the validator to drive async checks from a plain
  sync `main()`. Fair game to use yourself while poking at your
  implementation by hand.

## What's required

Implement both functions in `src/bridge.py`.

`process_batch(items, blocking_lib, max_workers)`:

1. **The event loop stays responsive for the whole call.** `blocking_lib`
   must never run on the event loop's own thread -- every call has to be
   offloaded to a worker thread while this coroutine `await`s the result
   without blocking anything else.
2. **Bounded offload concurrency.** At most `max_workers` calls to
   `blocking_lib` may be in flight at any single instant, no matter how
   large `items` is -- but the cap should actually be USED: with enough
   items, multiple calls should genuinely run at once, not serialize down
   to one-at-a-time.
3. **Results come back in INPUT order.** `results[i]` corresponds to
   `items[i]`, regardless of which offloaded call finishes first.

`sync_entrypoint(items, blocking_lib, max_workers)`:

1. Must actually run `process_batch(...)` to completion and return its
   result -- not an unawaited coroutine object.
2. Must be callable from plain sync code with no event loop already running
   on the current thread (the normal top-level case). It does not need to
   handle being called from a thread where a loop is already running
   elsewhere.

You have design freedom in exactly which stdlib primitives you reach for
(see hints if you want a nudge). The validator only checks the observable
properties above.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Calibrates the achievable heartbeat tick rate on the machine it's running
  on, then runs a cheap heartbeat coroutine concurrently with
  `process_batch()` over a batch whose `blocking_lib` genuinely blocks its
  thread (`time.sleep`, not `asyncio.sleep`). Asserts the observed ticks
  stay close to what the calibration measured as achievable -- an
  implementation that calls `blocking_lib` inline collapses ticks to ~0 for
  the whole batch.
- Runs `process_batch()` over enough items that `blocking_lib`'s
  lock-protected in-flight counter can prove both halves of bounded
  concurrency: it never exceeds `max_workers`, and it actually reaches
  `max_workers` (the cap is used, not serialized to one at a time).
- Runs `process_batch()` over items with deliberately mismatched durations
  and asserts the results come back in input order, not completion order.
- Calls `sync_entrypoint(...)` from plain synchronous code and asserts it
  returns the correct list.
- Prints `PASSED` with the observed numbers, or `NOT PASSED: <reason>` and
  exits 1 on any failure -- including the stub still raising
  `NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- `asyncio.to_thread` vs `loop.run_in_executor` -- what each buys you and
  which executor `to_thread` uses by default
- Sizing and bounding a thread pool's concurrent work (an unbounded
  offload has its own failure mode -- it isn't "free" just because it's off
  the loop's thread)
- `asyncio.gather`'s ordering guarantee -- how it relates results to the
  order of the awaitables you passed it, independent of completion order
- The GIL and why `time.sleep`/blocking I/O in a worker thread does not
  stall the event loop the way it would inline
- `asyncio.run` -- why it's a top-level entry point, and what error it
  raises if called from an already-running loop
- The difference between "calling a coroutine function" and "running the
  coroutine it returns"
- `asyncio.run_coroutine_threadsafe` -- not needed for this task, but worth
  knowing when a sync caller needs to schedule work onto a loop that's
  already running on a different thread

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
mock-peer semantics, and generation details for the whole module --
spoilers. Don't read it before finishing this task.
