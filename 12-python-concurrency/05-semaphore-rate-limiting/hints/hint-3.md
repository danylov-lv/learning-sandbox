A concrete walk-through, no code, for one reasonable shape (token bucket +
semaphore):

1. Build one `asyncio.Semaphore(max_concurrency)`, shared across every
   path's fetch -- created once, outside the per-path coroutines, so they
   all contend on the same instance.
2. Build one rate limiter, also shared across every path's fetch. For a
   token bucket: track a token count (starting full, or starting at
   `rate_per_sec` if you want to allow an initial burst up to the ceiling)
   and a "last refill" timestamp. Give it one async method, something like
   `await limiter.acquire()`, that: computes how much time has passed since
   the last refill, adds `elapsed * rate_per_sec` tokens (capped at some
   max, e.g. `rate_per_sec` itself), updates the last-refill timestamp, and
   then either consumes a token and returns immediately (if `tokens >= 1`)
   or sleeps a bit and retries (if not). Guard the read-modify-write of the
   token count so two coroutines calling `acquire()` at the same instant
   don't both decide a token is available when only one really is (they're
   not truly parallel since this is a single-threaded event loop, but
   between an `await asyncio.sleep(...)` and re-checking, another coroutine
   can run -- think about where the actual mutation of the shared token
   count needs to happen relative to any `await` inside `acquire()`).
3. For each path, write a small per-path coroutine that: acquires the rate
   limiter (waits for a token), acquires the semaphore (waits for a free
   concurrency slot), performs the actual HTTP GET and reads the body,
   releases the semaphore, and returns `(path, body)`.
4. Schedule all per-path coroutines to run concurrently (e.g. `asyncio.
   gather` over them, or an `asyncio.TaskGroup` -- either is fine here since
   you want all of them to run to completion, not to react to one failing by
   cancelling the rest). Because both gates are shared, `gather`ing all of
   them still respects both ceilings globally, not per-path.
5. Collect the `(path, body)` pairs into the returned dict.
6. Raise on any non-2xx response instead of storing it -- storing a 429's
   error body as if it were real data would silently corrupt the result and
   also means your limiter genuinely isn't working.

The order in step 3 (rate limiter before semaphore) versus the reverse both
respect both ceilings; think about which one leaves a coroutine "holding" a
scarce resource (a concurrency slot) while it's merely waiting its turn for
the other gate, and whether that's wasteful.
