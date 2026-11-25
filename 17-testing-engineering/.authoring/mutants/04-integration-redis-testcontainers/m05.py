"""BUG: `RateLimiter`'s Lua script calls `EXPIRE` on *every* call, not just
the one that opens the window.

The `if count == 1 then ... end` guard around `EXPIRE` is gone, so every
single call -- including denied ones -- pushes the key's TTL back out to
the full `window_seconds`. As long as calls (allowed or denied) keep
arriving more often than `window_seconds` apart, the key's TTL never
actually reaches zero and the window never closes: a caller that keeps
hammering a key stays rate-limited forever instead of getting a fresh
window. The boundary count itself (`limit` allowed, next denied) is
unaffected, so a pure boundary test does not catch this; a test that reads
the key's remaining TTL after a second call and asserts it did not jump
back up to the full window does.
"""

from __future__ import annotations

import redis


class RateLimiter:
    _LUA_ALLOW = """
    local count = redis.call('INCR', KEYS[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
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
