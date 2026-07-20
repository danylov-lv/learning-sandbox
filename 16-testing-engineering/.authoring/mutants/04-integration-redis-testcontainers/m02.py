"""BUG: `RateLimiter.allow` replaces the atomic Lua check-and-increment with
a two-round-trip GET-then-INCR, and the comparison is off by one on top of
that.

It reads the current count, allows the call if `current <= limit`, and
*then* increments. Walk it through sequential calls with `limit=3`: call 1
sees `current=0` (allowed, count becomes 1), call 2 sees `current=1`
(allowed, becomes 2), call 3 sees `current=2` (allowed, becomes 3), and
call 4 sees `current=3` -- `3 <= 3` is true, so it is *also* allowed,
becoming 4. Four calls get through a limit of three. This is deterministic
even single-threaded (no concurrency needed to observe it), and it is also
genuinely non-atomic: two separate round trips instead of one, leaving a
real race window under concurrent callers. A boundary test (assert exactly
`limit` calls succeed, the next fails) kills this.
"""

from __future__ import annotations

import redis


class RateLimiter:
    def __init__(self, client: redis.Redis, prefix: str = "ratelimit") -> None:
        self._client = client
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        full_key = self._redis_key(key)
        current = self._client.get(full_key)
        current = int(current) if current is not None else 0
        if current <= limit:
            new_count = self._client.incr(full_key)
            if new_count == 1:
                self._client.expire(full_key, window_seconds)
            return True
        return False


class DedupFilter:
    def __init__(self, client: redis.Redis, ttl_seconds: int, prefix: str = "dedup") -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def seen(self, key: str) -> bool:
        was_new = self._client.set(self._redis_key(key), "1", nx=True, ex=self._ttl_seconds)
        return was_new is None
