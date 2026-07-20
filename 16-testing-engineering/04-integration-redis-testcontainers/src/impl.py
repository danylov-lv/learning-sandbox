"""Correct implementation -- GIVEN, do not edit.

Two small Redis-backed components for a scraping pipeline, both built on
`redis-py` (a `redis.Redis` client is passed in; neither class owns
connection lifecycle -- that is the caller's job, see `tests/conftest.py`'s
fixtures for this task):

- `RateLimiter` -- a fixed-window rate limiter. `allow(key, limit,
  window_seconds)` returns `True` for the first `limit` calls for a given
  `key` within a window, `False` after that, and the window resets
  `window_seconds` after the *first* call in it (not after every call).
- `DedupFilter` -- a "have I seen this URL recently" filter. `seen(key)`
  records `key` with a TTL and returns whether it was already present, so
  the same URL is not reprocessed within the TTL but becomes eligible again
  once it expires.

Both do the check-and-write in a single atomic Redis operation (a Lua
`EVAL` for the limiter, `SET ... NX EX` for the filter) so there is no
window between "read the current state" and "write the new state" for a
concurrent caller to race through, and both TTL the keys they write so
nothing leaks forever. Both namespace their keys under a prefix so a
limiter and a filter (or two limiters for different purposes) never
collide even if called with the same logical `key` string.

The learner reads this file to understand the contract, then writes
`tests/test_redis_component.py` against it, running against a real,
ephemeral Redis via `testcontainers`. It is not itself a spoiler: the task
is "write an integration test suite that would catch a regression here",
not "reimplement this".
"""

from __future__ import annotations

import redis


class RateLimiter:
    """Fixed-window rate limiter backed by Redis.

    Each `(prefix, key)` pair gets its own counter. The counter and its TTL
    are set together in one Lua script so a concurrent burst of callers
    against the same key cannot slip more than `limit` of them through --
    there is no separate "read the count, then decide" step to race.
    """

    # KEYS[1] = the namespaced counter key, ARGV[1] = limit, ARGV[2] = window
    # seconds. INCR always happens; EXPIRE only fires on the call that
    # creates the key (count == 1), so a later call within the same window
    # never pushes the expiry back out -- the window closes on schedule.
    _LUA_ALLOW = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[2])
    end
    if count > tonumber(ARGV[1]) then
        return 0
    end
    return 1
    """

    def __init__(self, client: redis.Redis, prefix: str = "ratelimit") -> None:
        self._client = client
        self._prefix = prefix
        self._allow_script = client.register_script(self._LUA_ALLOW)

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True iff this call is within `limit` for the current window.

        The first `limit` calls for `key` in a `window_seconds` window
        return True; the `limit + 1`-th and any further call in that same
        window return False. A fresh window starts `window_seconds` after
        the first call that opened the previous one, at which point the
        counter resets and a new window begins.
        """
        result = self._allow_script(keys=[self._redis_key(key)], args=[limit, window_seconds])
        return bool(int(result))


class DedupFilter:
    """"Have I seen this key before" filter backed by Redis, with a TTL.

    A key is considered "seen" for `ttl_seconds` after the first time it is
    passed to `seen()`. Recording and checking happen in one atomic `SET
    key val NX EX ttl` call: `NX` makes the write a no-op if the key
    already exists, so there is no separate exists-check-then-set race, and
    the return value of that single call is exactly what tells us whether
    the key was new.
    """

    def __init__(self, client: redis.Redis, ttl_seconds: int, prefix: str = "dedup") -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def seen(self, key: str) -> bool:
        """Record `key` and return whether it was already present.

        Returns False the first time `key` is passed in (and records it,
        due to expire in `ttl_seconds`). Returns True for every call within
        `ttl_seconds` of that first call. Once the TTL elapses, the key is
        gone and the next `seen()` call for it returns False again.
        """
        was_new = self._client.set(self._redis_key(key), "1", nx=True, ex=self._ttl_seconds)
        return was_new is None
