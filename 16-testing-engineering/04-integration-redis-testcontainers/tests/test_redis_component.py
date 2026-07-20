"""YOUR DELIVERABLE -- integration tests for `RateLimiter`/`DedupFilter`
against a real Redis.

Read `src/impl.py` first (the docstrings on `RateLimiter.allow` and
`DedupFilter.seen` are the contract). Import the things under test from
`src.sut`, not `src.impl` -- that indirection is how grading swaps in a
mutant implementation:

    from src.sut import RateLimiter, DedupFilter

Use the `redis_client` fixture from `tests/conftest.py` (a real client
against an ephemeral `redis:7` container, flushed before every test) to
construct `RateLimiter(redis_client)` / `DedupFilter(redis_client,
ttl_seconds=...)` and, where useful, to inspect keys directly (`.ttl()`,
`.pttl()`, `.pexpire()`) rather than sleeping.

Write real `def test_*(redis_client):` functions below. This file
currently has none, so `python -m pytest` collects 0 tests and fails --
that is expected until you add some. See `hints/` if you get stuck, and
`../README.md` for the completion criteria.

Areas the grading mutant bank specifically probes -- your suite needs at
least one test that would fail if any of these broke:

  - Rate-limit boundary: for a fresh key, exactly `limit` calls to
    `allow()` return True and the very next one returns False -- not
    `limit - 1`, not `limit + 1`.
  - TTL is actually set: after a call to `allow()` or `seen()`, the
    underlying Redis key must have a TTL greater than zero. A key with no
    TTL leaks forever.
  - The window does not get pushed back: a call that happens *after* the
    window has already been opened must not reset the remaining TTL back
    up to the full window -- only the call that opens a fresh window sets
    the TTL.
  - Window reset: once the window's TTL has actually elapsed, `allow()`
    for that key must behave like a fresh key again (the first `limit`
    calls succeed). Control this via a short window or by manipulating the
    key's own TTL (`.pexpire()`) rather than a long `time.sleep()`.
  - Namespace isolation: two different keys (or a `RateLimiter` and a
    `DedupFilter` fed the *same* logical key string) must never share
    state.
  - Dedup correctness: the first `seen(key)` call for a fresh key returns
    False; a second call for that same key, before the TTL elapses,
    returns True.

Avoid wall-clock sleeps longer than about a second -- prefer short windows
and TTL introspection (`.ttl()` / `.pttl()`) or forcing a key's TTL down
with `.pexpire()` to simulate time passing.
"""

from __future__ import annotations

from src.sut import DedupFilter, RateLimiter  # noqa: F401

# TODO: write test_* functions here, each taking the `redis_client` fixture.
