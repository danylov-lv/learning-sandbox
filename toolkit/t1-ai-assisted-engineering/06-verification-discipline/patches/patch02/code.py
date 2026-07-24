"""In-memory pagination helper for the /records endpoint."""

from __future__ import annotations


def paginate(items: list, page: int, page_size: int) -> list:
    """Return the `page`-th page (0-indexed) of `items`, `page_size`
    items per page."""
    start = page * page_size
    end = start + page_size - 1
    return items[start:end]
