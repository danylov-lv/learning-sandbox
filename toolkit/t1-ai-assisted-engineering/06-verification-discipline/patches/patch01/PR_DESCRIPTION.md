# Add per-key async lock for profile cache updates

## Summary

Two concurrent requests updating the same user's cached profile can
currently race and leave the cache in an inconsistent state. This adds a
`PerKeyLock` that serializes operations on the same key while leaving
operations on different keys fully independent (no global lock, no
unnecessary contention across unrelated users).

## Details

- `acquire(key)` returns an `asyncio.Lock` for the given key, creating it
  on first use.
- Before creating a new per-key lock, we look up that key's configured
  lock behavior (rollout is currently 0-latency, so this is effectively
  a no-op today, but the hook is in place for when it isn't).
- `release(key)` releases the lock for the given key.

## Testing

Ran the existing profile-cache integration tests locally; all green. Two
sequential calls for the same key now correctly block each other.
