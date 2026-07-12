"""s11.t09 capstone -- a bounded async scraping pipeline.

This is where everything the module built gets assembled into one thing that
has to work at once, against a peer that is slow, capped, and (in CP2)
actively hostile:

  * task 02's structured concurrency (`asyncio.TaskGroup`) -- so a fan-out of
    "fetch every path" cannot leave an orphaned request running after this
    function returns or raises.
  * task 03's cancellation/timeout discipline -- a per-request deadline via
    `asyncio.timeout`, and a retry loop that never swallows a real
    cancellation, never leaks the resources (connections, tasks) it acquired
    along the way.
  * task 04's backpressure -- a bounded `asyncio.Queue` sitting between the
    stage that FETCHES pages and the stage that AGGREGATES them, so a fast
    fetch stage cannot run arbitrarily far ahead of a slower aggregate stage
    and pile up unbounded in-memory state. (The aggregation here is cheap,
    but the shape -- bounded queue between two independently-paced stages --
    is the point; a real pipeline's aggregate/persist stage would not be.)
  * task 05's semaphore-bounded concurrency -- the peer enforces a hard
    concurrency ceiling and returns HTTP 429 the instant you exceed it (see
    `harness/peer.py`); you must self-limit with an `asyncio.Semaphore`
    (or equivalent) so you never even attempt to cross it.

The story: `paths` is the full list of product-page URLs on a partner site
(`/p/1`, `/p/2`, ... `/p/n`). You need to fetch every one and produce an
aggregate: total count, total price, and a per-category count -- think "the
nightly job that reconciles our view of the partner's catalog." In steady
state (CP1) the peer is merely slow. Under chaos (CP2) it also fails some
fraction of requests with HTTP 500 and its latency jitters -- and the job
still has to converge to the exact same aggregate it would have produced
against a perfectly healthy peer, because a partial or silently-corrupted
catalog view is worse than a slow one.

Implement `scrape` below.
"""

import asyncio


async def scrape(
    peer,
    paths: list[str],
    *,
    max_concurrency: int,
    queue_maxsize: int = 32,
    max_retries: int = 3,
    request_timeout: float = 5.0,
) -> dict:
    """Fetch every path in `paths` from `peer` and return the aggregate.

    Args:
        peer: a `harness.peer.Peer` (see `harness/peer.py`) -- a live,
            already-running mock HTTP peer. Build request URLs with
            `peer.url(path)`; you open your own `aiohttp.ClientSession`
            against it (or sessions -- your call, but see the "no leaked
            connections" guarantee below). Each successful response body is
            JSON: `{"product_id": int, "category": str, "price": float}`.
        paths: the full list of paths to fetch, e.g. `["/p/1", "/p/2", ...,
            "/p/n"]`. Order does not matter for the returned aggregate (sums
            and counts are commutative) -- you are free to fetch and
            aggregate in whatever order is convenient.
        max_concurrency: the maximum number of requests you may have
            simultaneously in flight against `peer`, ever. This is a HARD
            ceiling the peer itself enforces: a request that would push the
            number of simultaneously in-flight handlers past this cap gets
            rejected with HTTP 429 before the peer does any work on it (see
            `harness/peer.py`'s "Concurrency gate"). Treat a 429 as a bug in
            your own limiting, not a response to retry your way past --
            self-limit with something like an `asyncio.Semaphore(
            max_concurrency)` so you never even attempt to cross the ceiling,
            rather than reacting to 429s after the fact.
        queue_maxsize: the bound on the queue sitting between your FETCH
            stage and your AGGREGATE stage. Structure this function as two
            cooperating stages, not one flat loop: a bounded number of
            fetcher coroutines (gated by the semaphore above) that each pull
            a path, fetch it, and PUT the parsed record onto a bounded
            `asyncio.Queue(maxsize=queue_maxsize)`; and a separate aggregator
            coroutine that GETs records off that queue and folds them into
            the running count/price_sum/per_category_count. `put()` on a
            full queue blocks -- that block is the backpressure: if the
            aggregate stage ever falls behind (imagine a real one that writes
            to a slow downstream store instead of just incrementing a dict),
            the fetch stage stalls with it instead of piling up an unbounded
            number of already-fetched-but-not-yet-aggregated records in
            memory. Do not fetch everything into a plain list first and
            aggregate afterward -- that has no backpressure at all and
            defeats the point of this parameter.
        max_retries: the maximum number of RETRIES (i.e. attempts beyond the
            first) allowed per path before giving up on it. A failed attempt
            is any of: a non-200 HTTP status (429 despite your own limiting,
            500 from injected chaos in CP2, or anything else unexpected), a
            per-request timeout (see `request_timeout` below), or a raised
            connection error. Retries should back off between attempts
            (a short fixed delay or a small exponential backoff, your
            choice, ideally with a low cap so a pathological run cannot
            stall) -- this task does not grade the exact backoff shape, only
            that failures are retried up to the cap rather than either (a)
            given up on instantly with no retry at all, or (b) retried
            forever with no cap. If every attempt for a path is exhausted,
            do not silently drop that path from the aggregate -- a silently
            incomplete catalog view is exactly the failure mode this
            function exists to prevent. Raise instead (any exception type
            that clearly identifies which path and how many attempts were
            made is fine) so the caller finds out loudly.
        request_timeout: seconds allowed for a single fetch ATTEMPT (one
            HTTP round trip, not the whole retry sequence) before it is
            cancelled and counted as a failed attempt eligible for retry.
            Wrap each individual attempt in something like
            `async with asyncio.timeout(request_timeout):` (or
            `asyncio.wait_for`) -- not the retry loop as a whole -- so a
            single slow/hanging attempt cannot stall the entire path
            indefinitely, and so that time already spent on the attempt
            that just timed out doesn't count against the next attempt's
            budget.

    Returns:
        A dict with exactly:
            "count": int -- number of pages successfully fetched (must
                equal `len(paths)` on success; every path contributes
                exactly once).
            "price_sum": float -- sum of every fetched page's `price`.
            "per_category_count": dict[str, int] -- number of fetched pages
                per distinct `category` value observed (only categories
                actually seen need to appear as keys).

    Guarantees this implementation must uphold, all simultaneously:

    1. Never exceeds `max_concurrency` simultaneous in-flight requests
       against `peer` -- self-enforced, not merely "usually stays under it."
    2. Genuinely uses concurrency -- fetching `paths` one at a time in a
       plain serial loop respects guarantee 1 trivially but is not what is
       being asked; the peer should observe real, bounded concurrency.
    3. Backpressure is real, not cosmetic: the fetch stage and the aggregate
       stage are connected by a bounded queue whose `put()` can actually
       block the fetch stage when the aggregate stage falls behind.
    4. Under CP2's injected errors and timeouts, every path still eventually
       succeeds (via retry) and contributes to the aggregate exactly once --
       the returned aggregate must be identical to what a perfectly healthy
       run over the same corpus would produce.
    5. No leaks, ever: whether `scrape` returns normally or raises (e.g.
       because a path exhausted its retries), every `asyncio.Task` it
       created must be finished by the time control returns to the caller
       (nothing left for `harness.common.leaked_tasks` to find), and every
       HTTP connection/session it opened must be closed (`async with` on
       your `aiohttp.ClientSession`, and on each response, is enough).
       Cancellation (from a per-request timeout, or from this coroutine
       itself being cancelled by an external caller) must propagate --
       never be caught and silently discarded.

    Raises:
        Whatever you choose to raise when a path exhausts `max_retries` (see
        `max_retries` above). Also propagates `asyncio.CancelledError` if
        this coroutine itself is cancelled from outside -- never swallow it.
    """
    raise NotImplementedError
