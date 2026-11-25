Two mechanisms, one for each ceiling:

**Concurrency**: `asyncio.Semaphore(max_concurrency)`. `await sem.acquire()`
(or `async with sem:`) before doing the actual request, release after. This
is the entire concurrency story -- nothing fancier is needed.

**Rate**: something time-aware that gates request *starts*, independent of
the semaphore. Three common shapes, in rough order of how much bookkeeping
they need:

- **Fixed spacing**: never let a new request start less than `1 /
  rate_per_sec` seconds after the previous one started. Simple, but a single
  shared "last start time" needs to be read-and-updated without a race
  between coroutines deciding to start at nearly the same instant (an
  `asyncio.Lock` around the check-and-update, or an `asyncio.Semaphore`-like
  primitive keyed on time, both work).
- **Token bucket**: a bucket holding up to some number of tokens, refilled
  at `rate_per_sec` tokens per second (either continuously by tracking
  elapsed time, or via a background task that adds a token periodically). A
  request must acquire a token before starting; if the bucket is empty, it
  waits. This is the standard answer and tolerates short bursts better than
  fixed spacing, since a full bucket lets several requests start close
  together before falling back to the steady rate.
- **Fixed window counter**: count starts within the current 1-second window;
  once you hit `rate_per_sec`, block new starts until the window rolls over.
  Simpler than a token bucket but has a burst edge at window boundaries (not
  a problem here, since you only need to *not exceed* the ceiling, not
  guarantee perfectly even spacing).

Whichever you pick, it needs to sit in the code path *before* a request is
allowed to start, exactly like the semaphore does, but checking a completely
different condition. Think about where each gate wraps the request: does the
order (acquire semaphore, then wait for a rate token, vs. the reverse)
matter for correctness here? (It doesn't change whether either ceiling gets
respected, but it does change what a coroutine is doing while it waits --
worth reasoning through either way.)
