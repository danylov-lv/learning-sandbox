CP2 adds two independent failure modes to a single fetch attempt: the peer
can return HTTP 500 (after already having spent the request's latency), and
an attempt can simply take too long. Both need to turn into "this attempt
failed, try again" rather than "this path is lost" or "this coroutine hangs
forever."

Wrap ONE ATTEMPT -- the single `session.get(...)` plus reading/parsing its
body -- in `async with asyncio.timeout(request_timeout):`, not the whole
retry loop. If you put the timeout around the retry loop instead, a
sequence of several fast-but-failing attempts can eat the whole budget
before a single one even gets a fair shot at succeeding, and worse, a
timeout firing mid-attempt would need to somehow "give back" unused time
to the next attempt, which `asyncio.timeout` doesn't do for you -- scoping
it per-attempt sidesteps both problems. When the timeout fires, catch the
resulting `TimeoutError` at the point where you decide "attempt failed,
should I retry" -- don't let it escape all the way out of `scrape()` for a
single slow attempt when a retry might well succeed.

The retry loop itself: attempt, and on failure (bad status code or a
caught `TimeoutError`/connection error), wait a short backoff and try
again, up to `max_retries` retries total for that one path. A fixed short
sleep between attempts is enough to pass; a small exponential backoff
(e.g. doubling, capped) is a nice touch but not required. What matters
more than the exact backoff shape: after the retry budget is exhausted for
a path, don't quietly move on to the next one as if nothing happened --
raise, with enough detail (which path, how many attempts) that whatever
catches it knows what actually broke. Silently under-counting is a subtler
bug than crashing, and this capstone's whole point is that the aggregate
must be trustworthy.

Two things to double check once retries are in: first, that a `finally` (or
equivalent) around each attempt's resource cleanup runs on every exit path
-- a timed-out attempt's response object and the semaphore slot it held
must both be released even though that attempt never got a normal `return`.
Second, run CP2 more than once locally -- the injected error rate and
jitter are randomized (deterministically, from a seeded RNG in the peer,
but the request-arrival-to-random-draw mapping isn't perfectly stable
across runs under real scheduling) enough that a retry loop with an
off-by-one in its cap, or a race in how it releases the semaphore on
failure, may pass once and fail the next run.
