"""BUG: `DedupFilter.seen` sets the key without a TTL (`EX` dropped).

`SET key val NX` still correctly reports "already present" vs "newly
recorded" -- the dedup boundary itself looks right -- but the key it
writes never expires. A URL marked seen stays marked seen forever instead
of becoming eligible again after `ttl_seconds`. A test that only checks
"first call False, second call True" does not catch this (that part still
works); a test that checks the underlying key actually has a TTL greater
than zero, or that the key expires and `seen()` returns False again after
the TTL, does.
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
        was_new = self._client.set(self._redis_key(key), "1", nx=True)
        return was_new is None
