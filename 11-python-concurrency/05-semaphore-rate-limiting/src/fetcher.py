"""s11.t05 -- fetch a batch of paths from a slow, easily-overloaded peer
without ever tripping its concurrency cap or its rate cap.

The peer (`harness.peer.mock_peer`) enforces TWO independent ceilings, and it
is deliberate that they are independent:

1. **Concurrency**: how many requests may be simultaneously in flight, at any
   single instant. Bounding this is what `asyncio.Semaphore` is for -- an
   `acquire()`/`release()` pair around each request body so no more than N
   coroutines are inside the "doing the request" section at once.
2. **Rate**: how many requests may *start* within any given second, measured
   over a sliding window, regardless of how many are simultaneously in
   flight. This is a fundamentally different quantity from concurrency, and a
   semaphore does not bound it.

Why you need both, concretely: suppose the peer allows `max_concurrency=8`
and `rate_per_sec=20`, and each request takes about 0.05s (`base_latency`).
A semaphore alone, sized to 8, happily keeps 8 requests in flight at all
times -- but as soon as one finishes (~0.05s later) the semaphore lets
another one start immediately. That steady-state throughput is roughly
`concurrency / latency = 8 / 0.05 = 160` requests per second -- eight times
over the 20/sec ceiling. The peer will reject the excess with HTTP 429 long
before you've fetched everything, even though you never had more than 8
requests in flight at once. Concurrency was never the problem; the rate at
which you were *starting* requests was.

The reverse can happen too: a rate limiter alone caps how often you start a
new request, but if nothing also caps how many outstanding requests you let
pile up (e.g. because responses arrive slower than you're issuing new
requests, or you fire off a `create_task` per path with no gate at all), you
can still have far more than `max_concurrency` requests in flight
simultaneously and trip that ceiling instead.

The naive, no-limits version of this function is a one-liner that will get
you banned by any real peer:

    async def fetch_all_naive(base_url, paths, session):
        results = await asyncio.gather(*(
            session.get(base_url + p) for p in paths
        ))
        ...

It has no notion of "at most N in flight" and no notion of "at most R
starts per second" -- it fires every request at once. Your job is to fetch
everything while never exceeding either ceiling, using a `Semaphore` for the
first and a separate time-based mechanism (a token bucket, a fixed-window
counter, or start-spacing -- your choice, see hints if you want a nudge) for
the second.

Implement `fetch_all` below.
"""


async def fetch_all(
    base_url: str,
    paths: list[str],
    max_concurrency: int,
    rate_per_sec: float,
) -> dict[str, bytes]:
    """Fetch every path in `paths` from `base_url`, returning `{path: body}`.

    Must never let more than `max_concurrency` requests be simultaneously in
    flight, AND must never start more than `rate_per_sec` requests within any
    trailing one-second window -- both ceilings are enforced by the peer
    itself (see module docstring), and exceeding either gets that request
    rejected with HTTP 429, which you must treat as a failure to fix, not a
    response to return.

    Args:
        base_url: passed straight to something like
            `base_url.rstrip("/") + path` (or use `aiohttp.ClientSession
            (base_url=...)`) to build each request URL.
        paths: every path to fetch, e.g. "/p/1", "/p/2", .... May contain
            more entries than `max_concurrency` -- that's the point.
        max_concurrency: the maximum number of requests you may have
            simultaneously in flight. Bound this with an `asyncio.
            Semaphore`.
        rate_per_sec: the maximum number of requests you may *start* within
            any trailing one-second window. This is a throughput cap over
            time, not an in-flight cap -- a semaphore alone cannot enforce
            it (see module docstring for why). You need a separate
            time-aware mechanism gating request starts.

    Returns:
        A dict mapping every path in `paths` to the raw response body
        (bytes) fetched from it. Every path must succeed -- if any request
        comes back as an error (e.g. HTTP 429 from tripping a ceiling, or
        HTTP 500), that is a bug in your limiting, not a result to store.

    Raises:
        NotImplementedError: until you implement it.
    """
    raise NotImplementedError
