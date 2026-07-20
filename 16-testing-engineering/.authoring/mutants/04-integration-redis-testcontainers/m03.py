"""BUG: neither class actually namespaces its Redis keys.

`_redis_key` in both `RateLimiter` and `DedupFilter` ignores `self._prefix`
and returns the caller's `key` verbatim. A `RateLimiter` and a
`DedupFilter` given the same logical key string (e.g. both called with
`"https://example.com/p/1"`) now read and write the *same* Redis key --
the limiter's integer counter and the filter's dedup marker collide, each
corrupting the other's state. Two `RateLimiter`s constructed with
different `prefix` values collide the same way. A namespace-isolation test
(same key string through a limiter and a filter, or through two
differently-prefixed instances, must not interfere) kills this; a test
that only ever uses one component at a time will not.
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
        return key

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        result = self._allow_script(keys=[self._redis_key(key)], args=[limit, window_seconds])
        return bool(int(result))


class DedupFilter:
    def __init__(self, client: redis.Redis, ttl_seconds: int, prefix: str = "dedup") -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return key

    def seen(self, key: str) -> bool:
        was_new = self._client.set(self._redis_key(key), "1", nx=True, ex=self._ttl_seconds)
        return was_new is None
