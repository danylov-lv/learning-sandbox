"""BUG: `RateLimiter`'s counter key is never given a TTL.

The Lua script does `INCR` but the `EXPIRE` call is gone entirely. The
counter keeps incrementing forever and never expires, so once a key hits
`limit` it stays denied permanently -- the window never resets, no matter
how long you wait. A test that only checks the boundary (exactly `limit`
allowed, the next denied) still passes against this mutant; only a test
that also checks the key has a TTL, or that the window actually resets,
catches it.
"""

from __future__ import annotations

import redis


class RateLimiter:
    _LUA_ALLOW = """
    local count = redis.call('INCR', KEYS[1])
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
        was_new = self._client.set(self._redis_key(key), "1", nx=True, ex=self._ttl_seconds)
        return was_new is None
