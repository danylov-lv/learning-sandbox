# 05 -- Semaphore + Rate Limiting

## Backstory

You've been handed a list of product pages to fetch from a partner's API.
Someone on your team already wrote the obvious first version:

```python
async def fetch_all_naive(base_url, paths, session):
    results = await asyncio.gather(*(
        session.get(base_url + p) for p in paths
    ))
    return {p: await r.read() for p, r in zip(paths, results)}
```

It works fine against a handful of paths in a quick local test. Pointed at
the real peer with sixty paths, it gets banned almost instantly: a wall of
HTTP 429s, most requests never completing. The partner's API is explicit
about why -- their docs list two separate limits: at most 8 requests may be
simultaneously in flight from your client, AND you may not start more than
20 requests per second, measured on a rolling basis. `asyncio.gather` over
every path at once respects neither.

The two limits are easy to conflate but are not the same thing, and fixing
only one of them is not enough:

- A **concurrency** limit bounds how many requests are open *at any single
  instant*. `asyncio.Semaphore(8)` is built for exactly this: acquire before
  a request, release after.
- A **rate** limit bounds how many requests may *start* within a trailing
  time window, independent of how many are simultaneously open. A semaphore
  says nothing about this: if requests are fast, a semaphore of size 8 will
  happily let request after request start the moment the previous one
  finishes, and that steady-state start rate can be many times higher than
  8 per second.

Concretely, against this peer: each request takes about 0.05s. A semaphore
sized to 8, saturated, lets a new request start roughly every 0.05s once the
pipeline is full -- about 160 starts per second. That's eight times over the
20/sec ceiling, and you'll get 429s well before you've fetched everything,
even though you never had more than 8 requests open at once. Concurrency was
never the problem.

The reverse failure mode also exists: a rate limiter alone caps how often
you *start* a request but says nothing about how many outstanding requests
you let pile up if responses are slow to drain -- you can still blow past a
concurrency ceiling with a "perfectly rate-limited" client that has no
concurrency gate at all. You need both controls, independently, at the same
time.

## What's given

- `src/fetcher.py` -- one function, `fetch_all(base_url, paths,
  max_concurrency, rate_per_sec)`, currently `raise NotImplementedError`.
  The docstring spells out the concurrency-vs-rate distinction and why a
  semaphore alone isn't sufficient.
- `harness/peer.py`'s `mock_peer` -- an in-process aiohttp server standing in
  for the partner API. Configured (by the validator) with both a
  `max_concurrency` and a `rate_per_sec`; a request that would exceed either
  gets HTTP 429 back immediately, without ever counting toward the other
  ceiling's tally. `peer.stats.throttled` counts every 429 you triggered;
  `peer.stats.max_observed_concurrency` is the peak number of simultaneously
  in-flight requests the peer ever saw from you.
- The harness's `run_async` and `leaked_tasks`/`snapshot_tasks` (see
  `harness/common.py`) -- used by the validator to also confirm you're not
  leaking `asyncio.Task`s (e.g. from a `create_task` whose handle you
  dropped without awaiting or cancelling it).

## What's required

Implement `fetch_all` in `src/fetcher.py` so that, fetching all given paths
from the peer:

1. No request ever pushes the number of simultaneously in-flight requests
   above `max_concurrency`.
2. No request ever pushes the number of request *starts* within any
   trailing one-second window above `rate_per_sec`.
3. Every path in `paths` ends up in the returned dict, mapped to its real
   response body -- an HTTP 429 (from tripping either ceiling) is a bug to
   fix, not a result to store.
4. You still use the concurrency you're given -- fetching everything one
   request at a time (effectively `max_concurrency=1` in spirit) respects
   both ceilings trivially but isn't what's being asked; the peer should see
   genuine concurrency, just bounded concurrency.
5. No `asyncio.Task` is created and abandoned without being awaited or
   cancelled.

You have design freedom in *how* you enforce the rate ceiling -- a token
bucket, a fixed-window counter, or simply spacing request starts apart by
`1 / rate_per_sec` are all valid, each with different burst characteristics.
The validator only observes the peer's stats and your results, not which
strategy you picked (see hints if you want a nudge on the tradeoffs).

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It spins up a mock peer with `max_concurrency=8` and `rate_per_sec=20`
(each request taking about 0.05s), asks your `fetch_all` to fetch ~60 paths
with those same limits, and asserts:

- `peer.stats.throttled == 0` -- you never tripped either ceiling.
- `peer.stats.max_observed_concurrency <= 8`.
- `peer.stats.max_observed_concurrency >= 2` -- you actually used
  concurrency, not a disguised serial loop.
- every path came back with its correct body.
- no leaked `asyncio.Task`s.

Prints `PASSED: ...` with the observed throttle count and peak concurrency,
or `NOT PASSED: <reason>` and exits 1 -- including the stub still raising
`NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- `asyncio.Semaphore` -- bounding concurrent sections of code
- Token bucket vs fixed-window vs sliding-window rate limiting
- The difference between a concurrency limit and a throughput/rate limit
- `asyncio.sleep` for pacing, and why sleeping inside a held semaphore slot
  is different from sleeping before acquiring one
- Structured concurrency and task leaks (why an abandoned `create_task`
  matters)

## Off-limits

`.authoring/` (at the module root) holds the harness API contract, the mock
peer's exact request-handling order, and the verification philosophy for
every task in this module -- spoilers. Don't read it before finishing this
task.
