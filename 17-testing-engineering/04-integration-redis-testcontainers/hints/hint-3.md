# Hint 3 -- concrete shape

A shape for each test, close to pseudocode. Fill in the actual
construction and assertions yourself -- this is not working code.

**Boundary:**

```
limiter = RateLimiter(redis_client)
results = [limiter.allow("some-key", limit=N, window_seconds=big) for _ in range(N + 1)]
# first N entries -> True, last entry -> False
```

**TTL is set (for both components):**

```
limiter.allow("some-key", limit=N, window_seconds=W)
# figure out the exact redis key this wrote (prefix + your key, see impl.py)
# assert redis_client.ttl(that_key) is > 0 (and <= W)
```

Do the equivalent for `DedupFilter.seen()` against its own key.

**Window not pushed back by a later call:**

```
limiter.allow(key, limit=N, window_seconds=W)   # W several seconds, not tiny
ttl_after_first = redis_client.pttl(that_key)
time.sleep(a few hundred ms, well under 1s)
limiter.allow(key, limit=N, window_seconds=W)   # second call, same key
ttl_after_second = redis_client.pttl(that_key)
# assert ttl_after_second is meaningfully LOWER than ttl_after_first,
# not back up near the full window
```

**Window reset without a real wait:**

```
limiter = RateLimiter(redis_client)
exhaust the limit against a fresh key (limit calls, last one denied)
find the exact redis key, force its TTL down: redis_client.pexpire(that_key, tiny_ms)
time.sleep(tiny_ms plus a small margin, still well under 1s)
# assert the next allow() call for that key behaves like a fresh key again
# (i.e. the first N calls succeed, not immediately denied)
```

**Namespace isolation:**

```
limiter = RateLimiter(redis_client)
dedup = DedupFilter(redis_client, ttl_seconds=big)
same_string = "shared-name"
exhaust limiter's limit for same_string
# assert dedup.seen(same_string) still behaves like a fresh key
# (i.e. its first call is False), proving the two do not share state
```

**Dedup correctness:**

```
dedup = DedupFilter(redis_client, ttl_seconds=big-enough-to-not-race-the-test)
# assert dedup.seen("some-url") is False (first time)
# assert dedup.seen("some-url") is True  (still within TTL)
```

Give each test a key string unique to that test (e.g. embed the test name)
so tests can never collide with each other even though they share one
container -- `flush_redis` clears everything between tests anyway, but
distinct keys make failures easier to read too.
