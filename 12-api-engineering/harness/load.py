"""A simple asyncio load bombardier (module 12) -- no locust dependency.

Fires concurrent requests at a URL (via a shared httpx.AsyncClient) or at a
learner-supplied async callable, for either a fixed duration or a fixed
request count, and reports honest percentile latencies computed from the
actually-collected sample (linear-interpolation percentile, same convention
numpy uses). Used by task 09's bottleneck-hunt validator and the capstone's
load-test checkpoint, and directly usable by the learner in their own
scripts. Every RPS/latency assertion built on top of this must be RELATIVE
(baseline.py + write_baseline/read_baseline), never an absolute number --
see design.md's verification philosophy.

Every third-party import (httpx) is lazy; importing this module has zero
side effects.
"""

import math
from dataclasses import dataclass


@dataclass
class LoadResult:
    total: int
    ok: int
    errors: int
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    elapsed_s: float


def _percentile(sorted_vals, p):
    """Linear-interpolation percentile over an already-sorted list."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[int(f)] * (c - k) + sorted_vals[int(c)] * (k - f)


async def bombard(url_or_fn, *, concurrency=10, duration_s=None, requests=None,
                   method="GET", client_kwargs=None, request_kwargs=None):
    """Fire requests at `url_or_fn` across `concurrency` concurrent workers.

    `url_or_fn`:
      - a `str` URL -- each worker does `client.request(method, url, **request_kwargs)`
        against one shared `httpx.AsyncClient(**client_kwargs)`.
      - an async callable `async def () -> response` -- each worker awaits it
        directly (the callable owns its own client/headers/auth/etc.); a
        "response" only needs a `.status_code` attribute (anything with one,
        e.g. an httpx.Response, qualifies as success if status < 400).

    Exactly one of `duration_s` (run for N seconds) or `requests` (run this
    many total requests, split across workers via a shared remaining-count)
    must be given.

    Returns a `LoadResult`. A request that raises any exception counts as an
    error, not a crash of the whole run.
    """
    import asyncio
    import time

    import httpx

    if duration_s is None and requests is None:
        raise ValueError("bombard() requires either duration_s or requests")

    request_kwargs = request_kwargs or {}
    client_kwargs = client_kwargs or {}

    is_url = isinstance(url_or_fn, str)
    shared_client = httpx.AsyncClient(**client_kwargs) if is_url else None

    latencies = []
    ok_count = [0]
    err_count = [0]
    remaining = [requests] if requests is not None else None
    deadline = time.monotonic() + duration_s if duration_s is not None else None

    async def _one_request():
        start = time.perf_counter()
        success = False
        try:
            if is_url:
                resp = await shared_client.request(method, url_or_fn, **request_kwargs)
                success = resp.status_code < 400
            else:
                resp = await url_or_fn()
                success = getattr(resp, "status_code", 200) < 400
        except Exception:
            success = False
        latencies.append((time.perf_counter() - start) * 1000.0)
        if success:
            ok_count[0] += 1
        else:
            err_count[0] += 1

    async def _worker():
        if remaining is not None:
            while True:
                if remaining[0] <= 0:
                    return
                remaining[0] -= 1
                await _one_request()
        else:
            while time.monotonic() < deadline:
                await _one_request()

    start_wall = time.perf_counter()
    try:
        await asyncio.gather(*(_worker() for _ in range(concurrency)))
    finally:
        if shared_client is not None:
            await shared_client.aclose()
    elapsed = time.perf_counter() - start_wall

    latencies.sort()
    total = len(latencies)
    rps = total / elapsed if elapsed > 0 else 0.0

    return LoadResult(
        total=total,
        ok=ok_count[0],
        errors=err_count[0],
        rps=rps,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        p99_ms=_percentile(latencies, 99),
        elapsed_s=elapsed,
    )
