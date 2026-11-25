"""BUG: `RateLimiter`'s boundary check is off by one -- the `limit`-th call
is wrongly denied.

The Lua script denies when `count >= limit` instead of `count > limit`.
Walk it through `limit=3`: call 1 makes `count=1` (`1 >= 3` false, allowed),
call 2 makes `count=2` (`2 >= 3` false, allowed), call 3 makes `count=3`
(`3 >= 3` true, DENIED). Only 2 calls get through a limit of 3, not 3. A
boundary test that asserts exactly `limit` calls succeed catches this;
a test that only checks "the first call is allowed" or "some call
eventually gets denied" does not.
"""

from __future__ import annotations

import redis


class RateLimiter:
    _LUA_ALLOW = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[2])
    end
    if count >= tonumber(ARGV[1]) then
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
