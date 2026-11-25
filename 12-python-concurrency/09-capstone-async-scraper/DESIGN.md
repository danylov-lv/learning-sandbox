# Capstone Design Memo -- Bounded Async Scraping Pipeline

Fill in each section with your own analysis, grounded in what you built and
observed across CP1 and CP2 of this capstone, and across tasks 01-05 of this
module (blocking-the-loop, TaskGroup, cancellation/timeouts, backpressure,
semaphore + rate limiting).

## Bounded concurrency and the semaphore

(fill in -- explain exactly how `scrape()` keeps the number of simultaneous
in-flight requests at or under `max_concurrency`, and why that has to be
self-enforced rather than left to the peer. What does `harness/peer.py`'s
concurrency gate actually do to a request that would exceed the cap, and why
does treating that as "a response to retry" rather than "a bug in your own
limiting" produce a worse scraper. Cite the actual `max_observed_concurrency`
CP1 and CP2 reported for your implementation, and say why it landed where it
did relative to the configured cap)

## Backpressure: the queue between fetch and aggregate

(fill in -- describe the two stages your implementation actually has: what
runs concurrently under the semaphore on the fetch side, what the aggregate
side does, and the bounded queue connecting them. What would have happened,
concretely, to memory behavior if you had fetched everything into a plain
list first and aggregated afterward instead -- why is that not "backpressure"
even though it eventually produces the same numbers. What does `queue_
maxsize` actually bound, and what determines whether the fetch stage or the
aggregate stage ends up being the slower one in your implementation)

## Cancellation, timeouts, and retries under chaos

(fill in -- walk through what happens to a single path's fetch when it times
out or gets an injected HTTP 500 under CP2: which exception fires, where your
retry loop catches it, and how the retry is bounded so a pathological run
cannot stall or retry forever. Explain precisely where `asyncio.timeout` (or
`asyncio.wait_for`) sits relative to the retry loop -- around one attempt or
around the whole sequence of attempts -- and why that placement matters. What
happens to an in-flight `aiohttp` request and its connection when its
attempt's timeout fires, and how do you know (from CP2's `leaked_tasks`
result and `peer.stats`) that nothing was left dangling)

## Failure modes and what would break convergence

(fill in -- beyond what CP2 actually tests, what else could go wrong in a
pipeline shaped like this one, and how would you detect or guard against
each: a path that fails every single retry attempt (what does your
implementation do, and why is silently dropping it worse than raising); a
consumer/aggregate stage that itself raises partway through a run and what
happens to fetch-stage tasks still in flight at that moment; a peer that
hangs indefinitely instead of returning an error; what would change in your
design if `paths` were ten million entries instead of a few thousand)
