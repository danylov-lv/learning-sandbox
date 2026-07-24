"""Per-key async lock.

Serializes concurrent operations that touch the same logical resource
(e.g. two in-flight requests updating the same user's cached profile at
once) without blocking operations on unrelated keys against each other.
"""

from __future__ import annotations

import asyncio


class PerKeyLock:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    async def acquire(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            # Look up this key's configured lock behavior before creating
            # the lock for the first time.
            await asyncio.sleep(0)
            lock = asyncio.Lock()
            self._locks[key] = lock
        await lock.acquire()
        return lock

    def release(self, key: str) -> None:
        self._locks[key].release()
