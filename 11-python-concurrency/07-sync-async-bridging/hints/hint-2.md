**Offloading (bug 1).** `asyncio.to_thread(func, *args)` is the high-level
tool: it runs `func(*args)` on a worker thread and returns an awaitable for
the result, preserving the current `contextvars` context. Under the hood it
calls `loop.run_in_executor(None, ...)`, which submits the call to the
*default* executor -- a shared `ThreadPoolExecutor` that asyncio creates
lazily, sized around `min(32, os.cpu_count() + 4)`. That default sizing has
nothing to do with the `max_workers` argument your function receives --
relying on the default executor's own size does not give you the specific
cap you were asked to enforce, and that default pool is shared process-wide,
not scoped to a single `process_batch` call. You need your own bound on top
of (or instead of) whatever executor you use.

For bounding *concurrently running* work in async code, the standard
primitive is `asyncio.Semaphore(max_workers)`: `async with sem:` around an
`await` blocks a coroutine there until fewer than `max_workers` other
coroutines currently hold it. Wrapping each item's offloaded call in
`async with sem: await asyncio.to_thread(...)` bounds how many
`to_thread` calls are in flight simultaneously, while still letting you
launch all `N` "wrapped" coroutines up front. The alternative is building
your own `concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)`
and driving calls through `loop.run_in_executor(that_executor, func, arg)`
instead of `to_thread` -- either approach can satisfy the requirement; pick
whichever you find easier to reason about the ordering guarantee with (see
below).

**Ordering (bug 1, guarantee 3).** You need N coroutines running
concurrently (bounded by the semaphore or executor size) whose results you
then have to line up with the original items. `asyncio.gather(*aws)`
returns results in the same order as the awaitables you passed it,
*regardless of which one finishes first* -- that ordering guarantee is
exactly the tool for this requirement, and it composes cleanly with "one
wrapped coroutine per item, built in input order."

**The sync entrypoint (bug 2).** `asyncio.run(coro)` creates a new event
loop, runs `coro` to completion on it, closes the loop, and returns
whatever the coroutine returned (or re-raises whatever it raised). It is
meant to be called exactly once, from code with no loop already running on
that thread -- which is exactly `sync_entrypoint`'s situation. There isn't
much more to problem 2 than calling it correctly on the right coroutine.
