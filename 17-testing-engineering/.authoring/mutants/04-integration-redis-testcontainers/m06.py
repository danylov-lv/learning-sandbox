"""BUG: `DedupFilter.seen` sets the key without the `NX` (not-exists) flag.

`SET key val EX ttl` without `NX` always succeeds and always returns a
truthy result, whether or not the key already existed -- it just
overwrites it. `seen()` is built on "was this SET a no-op because the key
was already there", so with `NX` gone it can never observe "already
there": every call, including the second and third for the exact same
key, reports False. A dedup test that only checks the very first call
("first `seen()` is False") does not catch this; a test that checks a
*second* call within the TTL returns True does.
"""

from __future__ import annotations

import redis


class RateLimiter:
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
        result = self._allow_script(keys=[self._redis_key(key)], args=[limit, window_seconds])
        return bool(int(result))


class DedupFilter:
    def __init__(self, client: redis.Redis, ttl_seconds: int, prefix: str = "dedup") -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def seen(self, key: str) -> bool:
        was_new = self._client.set(self._redis_key(key), "1", ex=self._ttl_seconds)
        return was_new is None
