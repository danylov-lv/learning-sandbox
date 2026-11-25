"""Bug: capacity is off by one. The cache is configured to hold at most
`capacity` live entries, but the eviction check here only fires once the
store holds `capacity + 1` entries, so the cache actually holds up to
`capacity + 1` items before it evicts anything.
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
        self._store.move_to_end(key)
        # BUG: should be `> self._capacity` -- this lets the store hold
        # one extra entry beyond the configured capacity.
        if len(self._store) > self._capacity + 1:
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
        self._store.move_to_end(key)
        return value

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)
