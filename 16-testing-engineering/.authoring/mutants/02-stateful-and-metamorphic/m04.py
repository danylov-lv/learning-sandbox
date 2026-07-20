"""Bug: `get()` no longer bumps recency on a hit. `put` still correctly
refreshes recency (for both new and existing keys), but reading a key via
`get` should ALSO mark it most-recently-used, and here it does not -- so a
key that was only ever read, never re-put, keeps aging toward eviction as
if it had never been touched.
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
        # BUG: missing self._store.move_to_end(key) -- a hit no longer
        # refreshes recency.
        return value

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)
