"""Bug: eviction order is FIFO (oldest-inserted) instead of LRU
(least-recently-used). Both `put` of an already-present key and a
successful `get` are supposed to refresh a key's recency so it is no
longer the next eviction candidate; here neither path does, so the only
thing that ever determines eviction order is original insertion order,
regardless of how often a key is touched afterward.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable, Hashable, Optional


class TTLCache:
    def __init__(
        self,
        capacity: int,
        ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        self._capacity = capacity
        self._ttl = ttl
        self._clock = clock
        self._store: "OrderedDict[Hashable, tuple[object, float]]" = OrderedDict()

    def _is_expired(self, deadline: float) -> bool:
        return self._clock() >= deadline

    def _purge_expired(self) -> None:
        expired = [k for k, (_, deadline) in self._store.items() if self._is_expired(deadline)]
        for k in expired:
            del self._store[k]

    def put(self, key: Hashable, value: object) -> None:
        self._purge_expired()
        deadline = self._clock() + self._ttl
        self._store[key] = (value, deadline)
        # BUG: no move_to_end() here -- an update to an existing key no
        # longer refreshes its recency, so order stays insertion order.
        if len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def get(self, key: Hashable) -> Optional[object]:
        self._purge_expired()
        entry = self._store.get(key)
        if entry is None:
            return None
        value, deadline = entry
        if self._is_expired(deadline):
            del self._store[key]
            return None
        # BUG: no move_to_end() here -- a hit no longer bumps recency.
        return value

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)
