"""t07 -- bridging synchronous and asynchronous code, in both directions.

This task is two related bugs, not one. Both come from treating "sync" and
"async" as if they mix for free -- they don't, and each direction breaks in
its own way.

PROBLEM 1 -- calling blocking code FROM an async service. Somewhere in a
service that's supposed to stay responsive, someone reaches for a
synchronous, genuinely-blocking third-party function (a driver that does
blocking network I/O, a CPU-bound transform, a library with no async variant
at all) and calls it directly on the hot path:

    async def process_batch_broken(items, blocking_lib):
        results = []
        for item in items:
            results.append(blocking_lib(item))  # BUG
        return results

This "works" in the sense that it returns the right answer. But
`blocking_lib(item)` is a plain synchronous call -- there is no `await` in
sight, so it never yields control back to the event loop. The event loop is
a single thread cooperatively multiplexing everything: every other
coroutine, every pending I/O callback, every timer, all of it lives on that
one thread and only gets a turn when the coroutine currently running hits an
`await` and gives control back. A synchronous call that blocks for real time
(sleeping, waiting on a socket, spinning the CPU) doesn't give control back
-- it just occupies the one thread the whole service depends on until it
returns. From the outside, the service looks completely frozen: no other
request is served, no timeout fires, no heartbeat ticks, for exactly as long
as `blocking_lib` takes. Looping over a batch like this doesn't parallelize
anything either -- each call still runs to completion, one after another, on
the same thread that's supposed to be free to do other work.

The fix is not "call it from a coroutine" (it already is one) -- it's
getting the blocking call OFF the event loop's thread entirely, onto a
worker thread, while the coroutine that requested it `await`s the result
without blocking anything else. That's what `asyncio.to_thread` and
`loop.run_in_executor` are for (see hints for which one and why).
Unbounded offloading has its own failure mode worth naming up front: firing
every item at a thread pool with no cap on how many run at once can still
exhaust threads, sockets, or whatever resource `blocking_lib` itself
consumes underneath -- offloading needs a bound, not just a different
thread.

PROBLEM 2 -- calling the async service FROM synchronous code. Suppose the
fixed, offloading-aware coroutine above is the thing you actually need to
call, but the caller is ordinary synchronous code -- a CLI entry point, a
plain function, a test, whatever -- with no event loop of its own. You
cannot just call a coroutine function and expect it to run:

    def sync_caller_broken(items, blocking_lib, max_workers):
        return process_batch(items, blocking_lib, max_workers)  # BUG: returns
        # an unawaited coroutine object, never actually runs

Calling a coroutine function only builds a coroutine object -- nothing
executes until something drives it on an event loop. `asyncio.run(coro)` is
that "something" for the common case: it creates a fresh event loop, runs
the coroutine to completion on it, tears the loop down, and returns the
result -- a clean synchronous-looking entry point into async code. Two
things to know about it before reaching for it:

- It is a TOP-LEVEL entry point, not something you sprinkle inside async
  code. Calling `asyncio.run(...)` from a coroutine that is itself already
  running on a loop raises `RuntimeError: asyncio.run() cannot be called
  from a running event loop` -- a thread can only have one event loop
  actively driving it at a time, and `asyncio.run` insists on creating and
  fully owning its own. If you're already inside `async def` code, you
  `await` things; you never `asyncio.run` them.
- If the caller that needs to drive async code is running on a DIFFERENT
  thread from the one that owns the loop (e.g. a GUI callback thread, or a
  request handler thread in a sync web framework, scheduling work onto a
  loop that's already running elsewhere), `asyncio.run` is the wrong tool
  entirely -- it wants to own the loop's entire lifetime on the calling
  thread. That situation calls for `asyncio.run_coroutine_threadsafe(coro,
  loop)`, which schedules a coroutine onto an event loop running on another
  thread and hands back a `concurrent.futures.Future` you can block on from
  the calling thread. This task's `sync_entrypoint` is the simpler top-level
  case -- no loop exists yet when it's called -- so `asyncio.run` is the
  right tool here; `run_coroutine_threadsafe` is worth knowing about, not
  something you need to reach for in this file.

Implement `process_batch` (fixes problem 1) and `sync_entrypoint` (fixes
problem 2) below.
"""


async def process_batch(items: list, blocking_lib, max_workers: int) -> list:
    """Run the synchronous, genuinely-blocking `blocking_lib(item)` for every
    item in `items`, without ever blocking the event loop, and without
    spawning more than `max_workers` concurrent offloaded calls.

    Required guarantees:

    1. The event loop stays responsive for the whole call. Nothing about how
       you invoke `blocking_lib` may occupy the event loop's own thread for
       any of `blocking_lib`'s execution time -- every call must run
       somewhere else (a worker thread) while this coroutine `await`s it.
       A validator proves this by running a cheap heartbeat coroutine
       concurrently with `process_batch` and counting how many times it
       ticks; a version that calls `blocking_lib` inline collapses this to
       near zero, because the event loop never gets a turn until the whole
       batch has already run synchronously to completion.

    2. Bounded offload concurrency. At most `max_workers` calls to
       `blocking_lib` may be in flight (actually executing, on a worker
       thread) at any single instant, no matter how large `items` is. Do
       not spawn one thread per item unbounded -- that defeats the purpose
       of a cap and can exhaust whatever resource `blocking_lib` itself
       depends on. At the same time, the cap should actually be USED: with
       enough items, multiple calls should be genuinely running at once (up
       to the cap), not serialized down to one-at-a-time.

    3. Results come back in INPUT order -- `results[i]` corresponds to
       `items[i]`, regardless of which offloaded call happened to finish
       first. Offloading to worker threads means completion order is not
       guaranteed to match input order unless you arrange for it.

    Args:
        items: the batch to process. Order matters for the return value
            (see guarantee 3); items themselves are opaque -- only ever
            passed to `blocking_lib`.
        blocking_lib: a synchronous callable, `blocking_lib(item) -> Any`.
            It performs real blocking work (sleeping, spinning, whatever the
            validator's stand-in does) and returns a value. Treat it as a
            third-party function you cannot modify or make async -- your
            job is entirely about HOW you call it, never rewriting it.
        max_workers: the maximum number of concurrent offloaded calls to
            `blocking_lib` allowed at any instant. Size this deliberately
            (see hints for how to think about a thread pool's size relative
            to what the blocking work actually costs) -- it is a hard cap
            the validator checks directly, not a suggestion.

    Returns:
        A list of results, one per item in `items`, in the same order as
        `items`.

    Raises:
        NotImplementedError: until you implement it.
    """
    raise NotImplementedError


def sync_entrypoint(items: list, blocking_lib, max_workers: int) -> list:
    """A plain SYNCHRONOUS function -- callable from ordinary sync code with
    no event loop of its own -- that drives `process_batch` to completion
    and returns its results.

    This is the boundary between synchronous callers (a CLI, a script, a
    test, a sync web framework's request handler) and the async machinery
    in `process_batch`. The caller of `sync_entrypoint` never touches
    `asyncio` at all -- it calls a normal function and gets back a normal
    list, exactly as if `process_batch` had been synchronous all along.

    Required guarantees:

    1. Must actually run `process_batch(items, blocking_lib, max_workers)`
       to completion and return its result -- not return an unawaited
       coroutine object, not run it on some already-running loop it doesn't
       own.
    2. Must be safe to call from code that has no event loop running on the
       current thread yet (the normal case for a top-level sync entry
       point). It is NOT required to handle being called from a thread that
       already has a loop running -- that is a different situation (see the
       module docstring's note on `run_coroutine_threadsafe`) that this
       function does not need to solve.

    Args:
        items, blocking_lib, max_workers: passed straight through to
            `process_batch` -- see its docstring for their meaning.

    Returns:
        Whatever `process_batch(items, blocking_lib, max_workers)` returns.

    Raises:
        NotImplementedError: until you implement it.
    """
    raise NotImplementedError
