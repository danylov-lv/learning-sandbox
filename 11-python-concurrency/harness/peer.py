"""In-process mock "slow peer" HTTP server for module 11 (Python
concurrency).

Tasks 01 (event-loop-and-blocking), 05 (semaphore-rate-limiting), and 09
(capstone-async-scraper) all need something that behaves like a slow,
occasionally-overloaded website to scrape against — without a docker
service. `mock_peer` starts a real aiohttp server in-process, bound to an
EPHEMERAL localhost port (`0`, resolved by the OS), so concurrent test runs
never collide on a fixed port.

Usage:

    async with mock_peer(base_latency=0.1, max_concurrency=5) as peer:
        async with aiohttp.ClientSession() as session:
            async with session.get(peer.url("/p/1")) as resp:
                ...
        peer.stats.max_observed_concurrency  # peak simultaneous in-flight handlers

Knobs (all keyword-only on `mock_peer`):

- `base_latency` (float, seconds) — every accepted request sleeps at least
  this long before responding, simulating a slow peer.
- `jitter` (float, seconds) — additional uniform(0, jitter) sleep added to
  `base_latency`, drawn from the peer's seeded RNG.
- `max_concurrency` (int | None) — if set, a request that would push the
  number of simultaneously in-flight handlers above this cap is rejected
  immediately with HTTP 429 (before sleeping) and `stats.throttled` is
  incremented. `None` means no concurrency cap.
- `rate_per_sec` (float | None) — if set, a request arriving when more than
  `rate_per_sec` requests have already reached this check within the
  trailing 1-second sliding window is rejected with HTTP 429 (before
  sleeping) and `stats.throttled` is incremented. `None` means no rate cap.
  Evaluated only for requests that passed the `max_concurrency` check (a
  request already rejected for concurrency does not also consume rate
  budget).
- `error_rate` (float, 0..1) — probability (per accepted, non-throttled
  request, drawn from the seeded RNG after the latency sleep) that the
  handler returns HTTP 500 instead of 200. `stats.error_responses` counts
  these.
- `seed` (int) — seeds the peer's private `random.Random` used for jitter
  and error-rate rolls, so behavior is reproducible run-to-run for a given
  request arrival pattern. (Under real concurrency, wall-clock scheduling
  order of coroutines is not itself deterministic, so exact draw-to-request
  assignment can vary; the *distribution* is reproducible.)
- `corpus` (dict[str, Any] | None) — if given and the request path (e.g.
  `/p/42`) is a key, its value is returned as the 200 body: `bytes`/
  `bytearray` values are returned raw, anything else is JSON-encoded. If
  `corpus` is `None` or the path is absent, the 200 body is the deterministic
  `{"path": path}`.

`Peer.stats` (a `PeerStats`) tracks, across the peer's lifetime:
- `total_requests` — every request that reached the handler (including ones
  later rejected with 429/500).
- `max_observed_concurrency` — peak simultaneous in-flight handlers that
  passed the `max_concurrency` gate (a request rejected with 429 never
  increments in-flight, so `max_observed_concurrency <= max_concurrency`
  always holds when the cap is set). The in-flight counter is incremented
  right after the gate, the max recorded, and it is decremented in a
  `finally` so it is accurate even when a handler is cancelled or raises.
- `error_responses` — count of injected HTTP 500s.
- `throttled` — count of injected HTTP 429s (concurrency cap or rate cap).
"""

import asyncio
import random
import socket
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiohttp import web


@dataclass
class PeerStats:
    total_requests: int = 0
    max_observed_concurrency: int = 0
    error_responses: int = 0
    throttled: int = 0


class Peer:
    def __init__(self, base_url, stats):
        self.base_url = base_url
        self.stats = stats

    def url(self, path):
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path


@asynccontextmanager
async def mock_peer(
    *,
    base_latency=0.05,
    jitter=0.0,
    max_concurrency=None,
    rate_per_sec=None,
    error_rate=0.0,
    seed=0,
    corpus=None,
):
    stats = PeerStats()
    rng = random.Random(seed)
    in_flight = 0
    arrivals = deque()

    async def handle(request):
        nonlocal in_flight
        path = "/" + request.match_info.get("path", "")
        stats.total_requests += 1

        # Gate BEFORE incrementing in-flight: a rejected arrival never counts
        # towards max_observed_concurrency, so the invariant
        # `max_observed_concurrency <= max_concurrency` always holds.
        if max_concurrency is not None and in_flight + 1 > max_concurrency:
            stats.throttled += 1
            return web.Response(status=429)

        in_flight += 1
        try:
            if in_flight > stats.max_observed_concurrency:
                stats.max_observed_concurrency = in_flight

            if rate_per_sec is not None:
                now = time.monotonic()
                cutoff = now - 1.0
                while arrivals and arrivals[0] < cutoff:
                    arrivals.popleft()
                arrivals.append(now)
                if len(arrivals) > rate_per_sec:
                    stats.throttled += 1
                    return web.Response(status=429)

            await asyncio.sleep(base_latency + (rng.uniform(0, jitter) if jitter > 0 else 0.0))

            if error_rate > 0 and rng.random() < error_rate:
                stats.error_responses += 1
                return web.Response(status=500)

            body = corpus.get(path) if corpus is not None else None
            if body is None:
                return web.json_response({"path": path})
            if isinstance(body, (bytes, bytearray)):
                return web.Response(body=body)
            return web.json_response(body)
        finally:
            in_flight -= 1

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)

    runner = web.AppRunner(app)
    await runner.setup()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    site = web.SockSite(runner, sock)
    await site.start()

    try:
        yield Peer(f"http://127.0.0.1:{port}", stats)
    finally:
        await runner.cleanup()
