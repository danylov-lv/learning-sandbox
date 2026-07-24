"""Chunk a list into fixed-size batches, e.g. for batched API calls."""

from __future__ import annotations


def chunk(items: list, size: int) -> list:
    """Split `items` into consecutive chunks of at most `size` elements
    each. The last chunk may be smaller than `size`. Raises ValueError if
    `size` is not positive."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i : i + size] for i in range(0, len(items), size)]
